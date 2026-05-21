#pragma once
#include <windows.h>
#include <string>
#include <userenv.h>

enum class ContainerResult {
    Created,
    AlreadyExists,
    Failed,
};

class AppContainer {
public:
    explicit AppContainer(const std::wstring& moniker);
    ~AppContainer();

    AppContainer(const AppContainer&) = delete;
    AppContainer& operator=(const AppContainer&) = delete;

    ContainerResult provision();
    HRESULT grant_path(const std::wstring& path, DWORD access_mask);
    PSID sid() const { return sid_; }

    static HRESULT reset(const std::wstring& moniker);

private:
    std::wstring moniker_;
    PSID sid_ = nullptr;
};
