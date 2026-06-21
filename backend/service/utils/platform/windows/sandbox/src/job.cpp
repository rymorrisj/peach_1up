#include "job.h"
#include <string>

JobObject::~JobObject() {
    if (handle_) {
        CloseHandle(handle_);
        handle_ = nullptr;
    }
}

HRESULT JobObject::create() {
    handle_ = CreateJobObjectW(nullptr, nullptr);
    if (!handle_) {
        return HRESULT_FROM_WIN32(GetLastError());
    }

    // Children inherit job membership and are killed when job closes.
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION eli = {};
    eli.BasicLimitInformation.LimitFlags =
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
        JOB_OBJECT_LIMIT_BREAKAWAY_OK;

    if (!SetInformationJobObject(handle_,
            JobObjectExtendedLimitInformation,
            &eli, sizeof(eli))) {
        return HRESULT_FROM_WIN32(GetLastError());
    }

    return S_OK;
}

HRESULT JobObject::apply_limits(const JobConfig& cfg) {
    if (!handle_) return E_HANDLE;

    JOBOBJECT_CPU_RATE_CONTROL_INFORMATION cpu = {};
#ifdef JOB_OBJECT_CPU_RATE_CONTROL_MIN_MAX_RATE
    // MIN_MAX_RATE requires Windows 10+ SDK headers.
    // Pack MinRate (low word) and MaxRate (high word) into the CpuRate field;
    // MinGW UCRT64 headers expose only CpuRate in the union.
    cpu.ControlFlags = JOB_OBJECT_CPU_RATE_CONTROL_ENABLE |
                       JOB_OBJECT_CPU_RATE_CONTROL_MIN_MAX_RATE;
    WORD min_w = static_cast<WORD>(cfg.cpu_min_rate * 100);
    WORD max_w = static_cast<WORD>(cfg.cpu_max_rate * 100);
    cpu.CpuRate = (static_cast<DWORD>(max_w) << 16) | static_cast<DWORD>(min_w);
#else
    // JOB_OBJECT_CPU_RATE_CONTROL_MIN_MAX_RATE is not available in this MinGW
    // installation (requires Windows 10+ SDK headers). Fall back to HARD_CAP.
    cpu.ControlFlags = JOB_OBJECT_CPU_RATE_CONTROL_ENABLE |
                       JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP;
    cpu.CpuRate = cfg.cpu_max_rate * 100;
#endif

    if (!SetInformationJobObject(handle_,
            JobObjectCpuRateControlInformation,
            &cpu, sizeof(cpu))) {
        return HRESULT_FROM_WIN32(GetLastError());
    }

    if (!cfg.skip_memory_limit && cfg.memory_limit_bytes > 0) {
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION eli = {};
        eli.BasicLimitInformation.LimitFlags =
            JOB_OBJECT_LIMIT_JOB_MEMORY |
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
            JOB_OBJECT_LIMIT_BREAKAWAY_OK;
        eli.JobMemoryLimit = cfg.memory_limit_bytes;

        if (!SetInformationJobObject(handle_,
                JobObjectExtendedLimitInformation,
                &eli, sizeof(eli))) {
            return HRESULT_FROM_WIN32(GetLastError());
        }
    }

    return S_OK;
}

HRESULT JobObject::assign(HANDLE process) {
    if (!handle_) return E_HANDLE;
    if (!AssignProcessToJobObject(handle_, process)) {
        return HRESULT_FROM_WIN32(GetLastError());
    }
    return S_OK;
}
