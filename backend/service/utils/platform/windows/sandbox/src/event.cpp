#include "event.h"
#include <sstream>

SandboxEvent::SandboxEvent(const std::wstring& moniker, DWORD pid) {
    std::wostringstream oss;
    oss << L"Local\\Sandbox_" << moniker << L"_" << pid;
    name_ = oss.str();
}

SandboxEvent::~SandboxEvent() {
    if (handle_) {
        CloseHandle(handle_);
        handle_ = nullptr;
    }
}

EventResult SandboxEvent::create() {
    handle_ = CreateEventW(
        nullptr,
        TRUE,   // manual reset
        FALSE,  // initially not signaled
        name_.c_str()
    );
    if (!handle_) return EventResult::Failed;
    return EventResult::Created;
}

HRESULT SandboxEvent::signal(const SignalState& /*state*/) {
    if (!handle_) return E_HANDLE;
    if (!SetEvent(handle_)) {
        return HRESULT_FROM_WIN32(GetLastError());
    }
    return S_OK;
}
