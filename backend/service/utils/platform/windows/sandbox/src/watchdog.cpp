#include "watchdog.h"

Watchdog::Watchdog(DWORD parent_pid, HANDLE done_event)
    : parent_pid_(parent_pid), done_event_(done_event) {}

Watchdog::~Watchdog() {
    stop();
}

void Watchdog::start() {
    stop_flag_.store(false);
    thread_ = std::thread(&Watchdog::monitor_loop, this);
}

void Watchdog::stop() {
    stop_flag_.store(true);
    if (thread_.joinable()) {
        thread_.join();
    }
}

void Watchdog::monitor_loop() {
    while (!stop_flag_.load()) {
        HANDLE parent = OpenProcess(SYNCHRONIZE, FALSE, parent_pid_);
        if (!parent) {
            // Parent is gone so signal the done event to trigger cleanup.
            SetEvent(done_event_);
            return;
        }
        CloseHandle(parent);
        Sleep(1000);
    }
}
