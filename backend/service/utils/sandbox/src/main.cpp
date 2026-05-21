#include <windows.h>
#include <sddl.h>
#include <string>
#include <vector>
#include <iostream>
#include <sstream>
#include <stdexcept>

#include "container.h"
#include "job.h"
#include "watchdog.h"
#include "event.h"

#include "json_parse.h"

// ── helpers ──────────────────────────────────────────────────────────────────

static std::wstring to_wide(const std::string& s) {
    if (s.empty()) return {};
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, nullptr, 0);
    std::wstring w(n - 1, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, w.data(), n);
    return w;
}

static std::string sid_to_string(PSID sid) {
    LPWSTR str = nullptr;
    if (!ConvertSidToStringSidW(sid, &str)) return "";
    std::wstring ws(str);
    LocalFree(str);
    return std::string(ws.begin(), ws.end());
}

static void emit_error(const std::string& stage,
                       const std::string& message,
                       bool disable_sandbox = false) {
    std::cout << JsonOut()
        .set("stage",           std::string("error"))
        .set("error_stage",     stage)
        .set("error",           message)
        .set("disable_sandbox", disable_sandbox)
        .set("sid",             std::string(""))
        .set("pid",             0LL)
        .set("event_name",      std::string(""))
        .dump() << "\n";
    std::cout.flush();
}

// ── LaunchConfig ─────────────────────────────────────────────────────────────

struct DaclGrant {
    std::wstring path;
    DWORD access_mask;
};

struct LaunchConfig {
    std::wstring moniker;
    std::wstring exe_path;
    std::vector<std::wstring> args;
    std::wstring working_dir;
    std::vector<DaclGrant> dacl_grants;
    JobConfig job_config;
    DWORD parent_pid;
};

static LaunchConfig parse_config(const JVal& j) {
    LaunchConfig cfg;
    cfg.moniker     = to_wide(j.at("moniker").get<std::string>());
    cfg.exe_path    = to_wide(j.at("exe_path").get<std::string>());
    cfg.working_dir = to_wide(j.value("working_dir", std::string{}));
    cfg.parent_pid  = j.at("parent_pid").get<DWORD>();

    for (auto& a : j.at("args").arr) {
        cfg.args.push_back(to_wide(a.get<std::string>()));
    }

    for (auto& g : j.at("dacl_grants").arr) {
        DaclGrant grant;
        grant.path        = to_wide(g.at("path").get<std::string>());
        grant.access_mask = g.at("access_mask").get<DWORD>();
        cfg.dacl_grants.push_back(std::move(grant));
    }

    auto& jc = j.at("job_config");
    cfg.job_config.cpu_max_rate        = jc.at("cpu_max_rate").get<DWORD>();
    cfg.job_config.cpu_min_rate        = jc.at("cpu_min_rate").get<DWORD>();
    cfg.job_config.skip_memory_limit   = jc.at("skip_memory_limit").get<bool>();
    SIZE_T mb = jc.at("memory_limit_mb").get<SIZE_T>();
    cfg.job_config.memory_limit_bytes  = mb * 1024 * 1024;

    return cfg;
}

// ── build command line ────────────────────────────────────────────────────────

static std::wstring build_cmdline(const std::wstring& exe,
                                  const std::vector<std::wstring>& args) {
    std::wostringstream oss;
    oss << L"\"" << exe << L"\"";
    for (auto& a : args) {
        oss << L" \"" << a << L"\"";
    }
    return oss.str();
}

// ── --reset mode ─────────────────────────────────────────────────────────────

static int run_reset(const std::string& moniker_utf8) {
    std::wstring moniker = to_wide(moniker_utf8);
    HRESULT hr = AppContainer::reset(moniker);
    if (FAILED(hr)) {
        std::cerr << "DeleteAppContainerProfile failed: 0x"
                  << std::hex << hr << "\n";
        return 1;
    }
    return 0;
}

// ── launch sequence ──────────────────────────────────────────────────────────

static int run_launch(const LaunchConfig& cfg) {
    // 1. Provision AppContainer.
    AppContainer container(cfg.moniker);
    auto cr = container.provision();
    if (cr == ContainerResult::Failed) {
        emit_error("CONTAINER_PROVISION",
                   "CreateAppContainerProfile failed");
        return 1;
    }

    // 2. Grant paths.
    for (auto& grant : cfg.dacl_grants) {
        HRESULT hr = container.grant_path(grant.path, grant.access_mask);
        if (FAILED(hr)) {
            std::ostringstream oss;
            oss << "grant_path failed (0x" << std::hex << hr << ")";
            emit_error("DACL_GRANT", oss.str());
            return 1;
        }
    }

    // 3. Create named event.
    // PID not known yet — use parent PID as part of the name for uniqueness.
    SandboxEvent evt(cfg.moniker, cfg.parent_pid);
    if (evt.create() == EventResult::Failed) {
        emit_error("PROCESS_CREATE", "CreateEventW failed");
        return 1;
    }

    // 4. Build SECURITY_CAPABILITIES for AppContainer.
    SECURITY_CAPABILITIES sc = {};
    sc.AppContainerSid = container.sid();

    SIZE_T attr_size = 0;
    InitializeProcThreadAttributeList(nullptr, 1, 0, &attr_size);
    std::vector<BYTE> attr_buf(attr_size);
    LPPROC_THREAD_ATTRIBUTE_LIST attr_list =
        reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attr_buf.data());
    if (!InitializeProcThreadAttributeList(attr_list, 1, 0, &attr_size)) {
        emit_error("PROCESS_CREATE", "InitializeProcThreadAttributeList failed");
        return 1;
    }
    if (!UpdateProcThreadAttribute(attr_list, 0,
            PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
            &sc, sizeof(sc), nullptr, nullptr)) {
        DeleteProcThreadAttributeList(attr_list);
        emit_error("PROCESS_CREATE", "UpdateProcThreadAttribute failed");
        return 1;
    }

    // 5. CreateProcessW — suspended, with EXTENDED_STARTUPINFO_PRESENT.
    STARTUPINFOEXW si = {};
    si.StartupInfo.cb = sizeof(si);
    si.lpAttributeList = attr_list;

    PROCESS_INFORMATION pi = {};

    std::wstring cmdline = build_cmdline(cfg.exe_path, cfg.args);
    LPCWSTR working_dir  = cfg.working_dir.empty() ? nullptr
                                                   : cfg.working_dir.c_str();

    DWORD create_flags = CREATE_SUSPENDED
                       | EXTENDED_STARTUPINFO_PRESENT;

    BOOL ok = CreateProcessW(
        cfg.exe_path.c_str(),
        cmdline.data(),
        nullptr, nullptr,
        FALSE,
        create_flags,
        nullptr,
        working_dir,
        &si.StartupInfo,
        &pi
    );

    DeleteProcThreadAttributeList(attr_list);

    if (!ok) {
        DWORD err = GetLastError();
        std::ostringstream oss;
        oss << "CreateProcessW failed (0x" << std::hex << err << ")";
        emit_error("PROCESS_CREATE", oss.str());
        return 1;
    }

    // 6. Breakaway retry — if already inside a Job that disallows breakaway.
    BOOL in_job = FALSE;
    IsProcessInJob(pi.hProcess, nullptr, &in_job);
    if (in_job) {
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);

        create_flags |= CREATE_BREAKAWAY_FROM_JOB;
        ok = CreateProcessW(
            cfg.exe_path.c_str(),
            cmdline.data(),
            nullptr, nullptr,
            FALSE,
            create_flags,
            nullptr,
            working_dir,
            &si.StartupInfo,
            &pi
        );
        if (!ok) {
            DWORD err = GetLastError();
            std::ostringstream oss;
            oss << "CreateProcessW (breakaway) failed (0x" << std::hex << err << ")";
            emit_error("PROCESS_CREATE", oss.str());
            return 1;
        }
    }

    // 7. Create Job, apply limits, assign process.
    JobObject job;
    if (FAILED(job.create())) {
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        emit_error("JOB_ASSIGN", "JobObject::create failed");
        return 1;
    }

    if (FAILED(job.apply_limits(cfg.job_config))) {
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        emit_error("JOB_ASSIGN", "JobObject::apply_limits failed");
        return 1;
    }

    if (FAILED(job.assign(pi.hProcess))) {
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        emit_error("JOB_ASSIGN", "JobObject::assign failed");
        return 1;
    }

    // 8. Resume.
    ResumeThread(pi.hThread);
    CloseHandle(pi.hThread);

    // 9. Emit startup JSON to stdout.
    std::wstring evt_name_w = evt.name();
    std::string evt_name(evt_name_w.begin(), evt_name_w.end());

    std::cout << JsonOut()
        .set("sid",        sid_to_string(container.sid()))
        .set("pid",        static_cast<long long>(pi.dwProcessId))
        .set("event_name", evt_name)
        .set("stage",      std::string("started"))
        .dump() << "\n";
    std::cout.flush();

    // 10. Watchdog.
    // Create a separate event for watchdog to signal when parent dies.
    HANDLE done_event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    Watchdog watchdog(cfg.parent_pid, done_event);
    watchdog.start();

    // 11. Wait for child process to exit OR watchdog to signal.
    HANDLE wait_handles[2] = { pi.hProcess, done_event };
    DWORD wait_result = WaitForMultipleObjects(2, wait_handles, FALSE, INFINITE);

    watchdog.stop();

    DWORD exit_code = 0;
    GetExitCodeProcess(pi.hProcess, &exit_code);
    CloseHandle(pi.hProcess);

    if (wait_result == WAIT_OBJECT_0 + 1) {
        // Parent died — kill child process tree (job object handles this).
        // Job destructor fires JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
    }

    CloseHandle(done_event);

    // 12. Signal the named event so Python watcher unblocks.
    SignalState ss;
    ss.state     = L"exited";
    ss.exit_code = static_cast<int>(exit_code);
    evt.signal(ss);

    return 0;
}

// ── entry point ───────────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    // --reset <moniker> mode.
    if (argc == 3 && std::string(argv[1]) == "--reset") {
        return run_reset(argv[2]);
    }

    // Launch mode: read JSON config from stdin.
    std::string input;
    {
        std::ostringstream oss;
        oss << std::cin.rdbuf();
        input = oss.str();
    }

    if (input.empty()) {
        emit_error("CONFIG_VALIDATION", "No JSON config received on stdin");
        return 1;
    }

    try {
        JVal j = json_parse(input);
        LaunchConfig cfg = parse_config(j);
        return run_launch(cfg);
    } catch (const std::exception& ex) {
        emit_error("CONFIG_VALIDATION",
                   std::string("JSON parse error: ") + ex.what());
        return 1;
    }
}
