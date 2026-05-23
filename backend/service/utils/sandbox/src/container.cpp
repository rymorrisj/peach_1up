#include "container.h"
#include <sddl.h>
#include <aclapi.h>
#include <stdexcept>

AppContainer::AppContainer(const std::wstring& moniker)
    : moniker_(moniker) {}

AppContainer::~AppContainer() {
    if (sid_) {
        FreeSid(sid_);
        sid_ = nullptr;
    }
    // Intentionally never calls DeleteAppContainerProfile — profile is stable
    // across launches for the same emulator moniker.
}

ContainerResult AppContainer::provision() {
    HRESULT hr = CreateAppContainerProfile(
        moniker_.c_str(),
        moniker_.c_str(),
        moniker_.c_str(),
        nullptr, 0,
        &sid_
    );

    if (SUCCEEDED(hr)) {
        return ContainerResult::Created;
    }

    if (hr == HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS)) {
        hr = DeriveAppContainerSidFromAppContainerName(moniker_.c_str(), &sid_);
        if (SUCCEEDED(hr)) {
            return ContainerResult::AlreadyExists;
        }
    }

    return ContainerResult::Failed;
}

HRESULT AppContainer::secure_existing_file(const std::wstring& path, DWORD access_mask) {
    if (!sid_) return E_POINTER;

    PACL existing_acl = nullptr;
    PSECURITY_DESCRIPTOR sd = nullptr;

    DWORD err = GetNamedSecurityInfoW(
        path.c_str(),
        SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION,
        nullptr, nullptr,
        &existing_acl, nullptr,
        &sd
    );
    if (err != ERROR_SUCCESS) return HRESULT_FROM_WIN32(err);

    EXPLICIT_ACCESS_W ea = {};
    ea.grfAccessPermissions = access_mask;
    ea.grfAccessMode        = GRANT_ACCESS;
    ea.grfInheritance       = NO_INHERITANCE;
    ea.Trustee.TrusteeForm  = TRUSTEE_IS_SID;
    ea.Trustee.TrusteeType  = TRUSTEE_IS_WELL_KNOWN_GROUP;
    ea.Trustee.ptstrName    = reinterpret_cast<LPWSTR>(sid_);

    PACL new_acl = nullptr;
    err = SetEntriesInAclW(1, &ea, existing_acl, &new_acl);
    if (sd) LocalFree(sd);
    if (err != ERROR_SUCCESS) return HRESULT_FROM_WIN32(err);

    err = SetNamedSecurityInfoW(
        const_cast<LPWSTR>(path.c_str()),
        SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION,
        nullptr, nullptr,
        new_acl, nullptr
    );
    if (new_acl) LocalFree(new_acl);

    return HRESULT_FROM_WIN32(err);
}

HRESULT AppContainer::grant_directory(const std::wstring& path, DWORD access_mask) {
    if (!sid_) return E_POINTER;

    PACL existing_acl = nullptr;
    PSECURITY_DESCRIPTOR sd = nullptr;

    DWORD err = GetNamedSecurityInfoW(
        path.c_str(),
        SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION,
        nullptr, nullptr,
        &existing_acl, nullptr,
        &sd
    );
    if (err != ERROR_SUCCESS) return HRESULT_FROM_WIN32(err);

    EXPLICIT_ACCESS_W ea = {};
    ea.grfAccessPermissions = access_mask;
    ea.grfAccessMode        = GRANT_ACCESS;
    ea.grfInheritance       = OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE;
    ea.Trustee.TrusteeForm  = TRUSTEE_IS_SID;
    ea.Trustee.TrusteeType  = TRUSTEE_IS_WELL_KNOWN_GROUP;
    ea.Trustee.ptstrName    = reinterpret_cast<LPWSTR>(sid_);

    PACL new_acl = nullptr;
    err = SetEntriesInAclW(1, &ea, existing_acl, &new_acl);
    if (sd) LocalFree(sd);
    if (err != ERROR_SUCCESS) return HRESULT_FROM_WIN32(err);

    err = SetNamedSecurityInfoW(
        const_cast<LPWSTR>(path.c_str()),
        SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION,
        nullptr, nullptr,
        new_acl, nullptr
    );
    if (new_acl) LocalFree(new_acl);

    return HRESULT_FROM_WIN32(err);
}

HRESULT AppContainer::reset(const std::wstring& moniker) {
    return DeleteAppContainerProfile(moniker.c_str());
}
