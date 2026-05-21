#pragma once
#include <windows.h>
#include <thread>
#include <atomic>

class Watchdog {
public:
    explicit Watchdog(DWORD parent_pid, HANDLE done_event);
    ~Watchdog();

    Watchdog(const Watchdog&) = delete;
    Watchdog& operator=(const Watchdog&) = delete;

    void start();
    void stop();

private:
    void monitor_loop();

    DWORD parent_pid_;
    HANDLE done_event_;  // not owned — caller manages lifetime
    std::thread thread_;
    std::atomic<bool> stop_flag_{false};
};
