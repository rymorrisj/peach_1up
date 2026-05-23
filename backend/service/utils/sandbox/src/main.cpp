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

static DWORD access_to_mask(const std::wstring& access) {
    if (access == L"rw") return 0x001201FF; // GENERIC_READ | GENERIC_WRITE
    return 0x00120089;                       // GENERIC_READ
}

// ── LaunchConfig ─────────────────────────────────────────────────────────────

struct BrokerFile {
    std::wstring path;
    std::wstring access; // "r" or "rw"
    std::wstring mode;   // "create", "inherit", or "grant"
};

struct LaunchConfig {
    std::wstring moniker;
    std::wstring exe_path;
    std::vector<std::wstring> args;
    std::wstring working_dir;
    std::vector<BrokerFile> broker_files;
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

    for (auto& f : j.at("broker_files").arr) {
        BrokerFile bf;
        bf.path   = to_wide(f.at("path").get<std::string>());
        bf.access = to_wide(f.at("access").get<std::string>());
        bf.mode   = to_wide(f.at("mode").get<std::string>());
        cfg.broker_files.push_back(std::move(bf));
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

// ── environment block helpers ─────────────────────────────────────────────────

static std::vector<wchar_t> build_env_block(const std::vector<std::wstring>& extra_vars) {
    std::vector<wchar_t> block;
    wchar_t* parent = GetEnvironmentStringsW();
    if (parent) {
        for (wchar_t* p = parent; *p; ) {
            size_t len = wcslen(p) + 1;
            block.insert(block.end(), p, p + len);
            p += len;
        }
        FreeEnvironmentStringsW(parent);
    }
    for (auto& var : extra_vars) {
        block.insert(block.end(), var.begin(), var.end());
        block.push_back(L'\0');
    }
    block.push_back(L'\0'); // double-null terminator
    return block;
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

    if (FAILED(container.grant_window_station())) {
        emit_error("CONTAINER_PROVISION", "grant_window_station failed");
        return 1;
    }

    // 2. Process broker_files.
    std::vector<HANDLE>       inherit_handles;
    std::vector<std::wstring> sandbox_env_vars;

    for (size_t i = 0; i < cfg.broker_files.size(); i++) {
        const BrokerFile& bf   = cfg.broker_files[i];
        DWORD             mask = access_to_mask(bf.access);

        if (bf.mode == L"secure") {
            container.secure_existing_file(bf.path, mask);

        } else if (bf.mode == L"inherit") {
            SECURITY_ATTRIBUTES sa = {};
            sa.nLength        = sizeof(sa);
            sa.bInheritHandle = TRUE;
            HANDLE h = CreateFileW(
                bf.path.c_str(), mask,
                FILE_SHARE_READ | FILE_SHARE_WRITE, &sa,
                OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr
            );
            if (h != INVALID_HANDLE_VALUE) {
                std::wostringstream oss;
                oss << L"SANDBOX_HANDLE_" << i << L"="
                    << static_cast<unsigned long long>(
                           reinterpret_cast<uintptr_t>(h));
                sandbox_env_vars.push_back(oss.str());
                inherit_handles.push_back(h);
            }

        } else if (bf.mode == L"grant") {
            container.grant_directory(bf.path, mask);
        }
    }

    // 3. Create named event.
    SandboxEvent evt(cfg.moniker, cfg.parent_pid);
    if (evt.create() == EventResult::Failed) {
        emit_error("PROCESS_CREATE", "CreateEventW failed");
        return 1;
    }

    // 4. Build SECURITY_CAPABILITIES and attribute list.
    SECURITY_CAPABILITIES sc = {};
    sc.AppContainerSid = container.sid();

    DWORD attr_count = inherit_handles.empty() ? 1 : 2;
    SIZE_T attr_size = 0;
    InitializeProcThreadAttributeList(nullptr, attr_count, 0, &attr_size);
    std::vector<BYTE> attr_buf(attr_size);
    LPPROC_THREAD_ATTRIBUTE_LIST attr_list =
        reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attr_buf.data());
    if (!InitializeProcThreadAttributeList(attr_list, attr_count, 0, &attr_size)) {
        emit_error("PROCESS_CREATE", "InitializeProcThreadAttributeList failed");
        return 1;
    }
    if (!UpdateProcThreadAttribute(attr_list, 0,
            PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
            &sc, sizeof(sc), nullptr, nullptr)) {
        DeleteProcThreadAttributeList(attr_list);
        emit_error("PROCESS_CREATE", "UpdateProcThreadAttribute (SECURITY_CAPABILITIES) failed");
        return 1;
    }
    if (!inherit_handles.empty()) {
        if (!UpdateProcThreadAttribute(attr_list, 0,
                PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                inherit_handles.data(),
                inherit_handles.size() * sizeof(HANDLE),
                nullptr, nullptr)) {
            DeleteProcThreadAttributeList(attr_list);
            emit_error("PROCESS_CREATE", "UpdateProcThreadAttribute (HANDLE_LIST) failed");
            return 1;
        }
    }

    // 5. Build environment block if inherit handles carry SANDBOX_HANDLE vars.
    std::vector<wchar_t> env_block;
    bool use_custom_env = !sandbox_env_vars.empty();
    if (use_custom_env) {
        env_block = build_env_block(sandbox_env_vars);
    }

    // 6. CreateProcessW — suspended, with EXTENDED_STARTUPINFO_PRESENT.
    STARTUPINFOEXW si = {};
    si.StartupInfo.cb = sizeof(si);
    si.lpAttributeList = attr_list;

    PROCESS_INFORMATION pi = {};

    std::wstring cmdline = build_cmdline(cfg.exe_path, cfg.args);
    LPCWSTR working_dir  = cfg.working_dir.empty() ? nullptr
                                                   : cfg.working_dir.c_str();
    BOOL inherit_h = inherit_handles.empty() ? FALSE : TRUE;

    DWORD create_flags = CREATE_SUSPENDED
                       | EXTENDED_STARTUPINFO_PRESENT;
    if (use_custom_env) create_flags |= CREATE_UNICODE_ENVIRONMENT;

    LPVOID env_ptr = use_custom_env
                     ? static_cast<LPVOID>(env_block.data())
                     : nullptr;

    BOOL ok = CreateProcessW(
        cfg.exe_path.c_str(),
        cmdline.data(),
        nullptr, nullptr,
        inherit_h,
        create_flags,
        env_ptr,
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

    // 7. Breakaway retry — if already inside a Job that disallows breakaway.
    BOOL in_job = FALSE;
    IsProcessInJob(pi.hProcess, nullptr, &in_job);
    if (in_job) {
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);

        // Rebuild attribute list for retry (attr_list was deleted above).
        attr_size = 0;
        InitializeProcThreadAttributeList(nullptr, attr_count, 0, &attr_size);
        attr_buf.assign(attr_size, 0);
        attr_list = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(attr_buf.data());
        InitializeProcThreadAttributeList(attr_list, attr_count, 0, &attr_size);
        UpdateProcThreadAttribute(attr_list, 0,
            PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
            &sc, sizeof(sc), nullptr, nullptr);
        if (!inherit_handles.empty()) {
            UpdateProcThreadAttribute(attr_list, 0,
                PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                inherit_handles.data(),
                inherit_handles.size() * sizeof(HANDLE),
                nullptr, nullptr);
        }
        si.lpAttributeList = attr_list;

        create_flags |= CREATE_BREAKAWAY_FROM_JOB;
        ok = CreateProcessW(
            cfg.exe_path.c_str(),
            cmdline.data(),
            nullptr, nullptr,
            inherit_h,
            create_flags,
            env_ptr,
            working_dir,
            &si.StartupInfo,
            &pi
        );
        DeleteProcThreadAttributeList(attr_list);
        if (!ok) {
            DWORD err = GetLastError();
            std::ostringstream oss;
            oss << "CreateProcessW (breakaway) failed (0x" << std::hex << err << ")";
            emit_error("PROCESS_CREATE", oss.str());
            return 1;
        }
    }

    // Close inheritable handles — child has inherited copies.
    for (HANDLE h : inherit_handles) CloseHandle(h);
    inherit_handles.clear();

    // 8. Create Job, apply limits, assign process.
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

    // 9. Resume.
    ResumeThread(pi.hThread);
    CloseHandle(pi.hThread);

    // 10. Emit startup JSON to stdout.
    std::wstring evt_name_w = evt.name();
    std::string evt_name(evt_name_w.begin(), evt_name_w.end());

    std::cout << JsonOut()
        .set("sid",        sid_to_string(container.sid()))
        .set("pid",        static_cast<long long>(pi.dwProcessId))
        .set("event_name", evt_name)
        .set("stage",      std::string("started"))
        .dump() << "\n";
    std::cout.flush();

    // 11. Watchdog.
    HANDLE done_event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    Watchdog watchdog(cfg.parent_pid, done_event);
    watchdog.start();

    // 12. Wait for child process to exit OR watchdog to signal.
    HANDLE wait_handles[2] = { pi.hProcess, done_event };
    DWORD wait_result = WaitForMultipleObjects(2, wait_handles, FALSE, INFINITE);

    watchdog.stop();

    DWORD exit_code = 0;
    GetExitCodeProcess(pi.hProcess, &exit_code);
    CloseHandle(pi.hProcess);

    if (wait_result == WAIT_OBJECT_0 + 1) {
        // Parent died — job object destructor kills child via JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
    }

    CloseHandle(done_event);

    // 13. Write exit JSON to stdout so the Python reader unblocks.
    std::cout << JsonOut()
        .set("stage",     std::string("exited"))
        .set("exit_code", static_cast<long long>(exit_code))
        .dump() << "\n";
    std::cout.flush();

    // 14. Signal the named event so Python watcher unblocks.
    SignalState ss;
    ss.state     = L"exited";
    ss.exit_code = static_cast<int>(exit_code);
    evt.signal(ss);

    return static_cast<int>(exit_code);
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
