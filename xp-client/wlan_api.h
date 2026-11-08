/* Minimal Wireless LAN API declarations for the XP SP3 subset.
   No Vista-only function or temporary-profile path is assumed. */
#ifndef HERMESXP_WLAN_API_H
#define HERMESXP_WLAN_API_H

typedef void *WLAN_HANDLE;
typedef unsigned long WLAN_DWORD;
typedef unsigned long WLAN_ULONG;
typedef unsigned short WLAN_WORD;
typedef unsigned char WLAN_BYTE;
typedef int WLAN_BOOL;
typedef unsigned short WLAN_WCHAR;
typedef struct { WLAN_DWORD Data1; WLAN_WORD Data2, Data3; WLAN_BYTE Data4[8]; } WLAN_GUID;

typedef struct {
    WLAN_ULONG uSSIDLength;
    WLAN_BYTE ucSSID[32];
} WLAN_DOT11_SSID;

typedef enum {
    wlan_interface_state_not_ready = 0,
    wlan_interface_state_connected = 1,
    wlan_interface_state_ad_hoc_network_formed = 2,
    wlan_interface_state_disconnecting = 3,
    wlan_interface_state_disconnected = 4,
    wlan_interface_state_associating = 5,
    wlan_interface_state_discovering = 6,
    wlan_interface_state_authenticating = 7
} WLAN_INTERFACE_STATE;

typedef struct {
    WLAN_GUID InterfaceGuid;
    WLAN_WCHAR strInterfaceDescription[256];
    WLAN_INTERFACE_STATE isState;
} WLAN_INTERFACE_INFO;

typedef struct {
    WLAN_DWORD dwNumberOfItems;
    WLAN_DWORD dwIndex;
    WLAN_INTERFACE_INFO InterfaceInfo[1];
} WLAN_INTERFACE_INFO_LIST;

typedef struct {
    WLAN_WCHAR strProfileName[256];
    WLAN_DOT11_SSID dot11Ssid;
    WLAN_DWORD dot11BssType;
    WLAN_ULONG uNumberOfBssids;
    WLAN_BOOL bNetworkConnectable;
    WLAN_DWORD wlanNotConnectableReason;
    WLAN_ULONG uNumberOfPhyTypes;
    WLAN_DWORD dot11PhyTypes[8];
    WLAN_BOOL bMorePhyTypes;
    WLAN_ULONG wlanSignalQuality;
    WLAN_BOOL bSecurityEnabled;
    WLAN_DWORD dot11DefaultAuthAlgorithm;
    WLAN_DWORD dot11DefaultCipherAlgorithm;
    WLAN_DWORD dwFlags;
    WLAN_DWORD dwReserved;
} WLAN_AVAILABLE_NETWORK;

typedef struct {
    WLAN_DWORD dwNumberOfItems;
    WLAN_DWORD dwIndex;
    WLAN_AVAILABLE_NETWORK Network[1];
} WLAN_AVAILABLE_NETWORK_LIST;

typedef enum {
    wlan_connection_mode_profile = 0,
    wlan_connection_mode_temporary_profile = 1,
    wlan_connection_mode_discovery_secure = 2,
    wlan_connection_mode_discovery_unsecure = 3,
    wlan_connection_mode_auto = 4,
    wlan_connection_mode_invalid = 5
} WLAN_CONNECTION_MODE;

typedef struct {
    WLAN_CONNECTION_MODE wlanConnectionMode;
    const WLAN_WCHAR *strProfile;
    const WLAN_DOT11_SSID *pDot11Ssid;
    WLAN_DWORD dot11BssType;
    WLAN_DWORD dwFlags;
} WLAN_CONNECTION_PARAMETERS;

typedef WLAN_DWORD (__attribute__((stdcall)) *PFN_WlanOpenHandle)(WLAN_DWORD, void *, WLAN_DWORD *, WLAN_HANDLE *);
typedef WLAN_DWORD (__attribute__((stdcall)) *PFN_WlanEnumInterfaces)(WLAN_HANDLE, void *, WLAN_INTERFACE_INFO_LIST **);
typedef WLAN_DWORD (__attribute__((stdcall)) *PFN_WlanScan)(WLAN_HANDLE, const WLAN_GUID *, const WLAN_DOT11_SSID *, const void *, void *);
typedef WLAN_DWORD (__attribute__((stdcall)) *PFN_WlanGetAvailableNetworkList)(WLAN_HANDLE, const WLAN_GUID *, WLAN_DWORD, void *, WLAN_AVAILABLE_NETWORK_LIST **);
typedef WLAN_DWORD (__attribute__((stdcall)) *PFN_WlanSetProfile)(WLAN_HANDLE, const WLAN_GUID *, WLAN_DWORD, const WLAN_WCHAR *, const WLAN_WCHAR *, WLAN_BOOL, void *, WLAN_DWORD *);
typedef WLAN_DWORD (__attribute__((stdcall)) *PFN_WlanConnect)(WLAN_HANDLE, const WLAN_GUID *, const WLAN_CONNECTION_PARAMETERS *, void *);
typedef WLAN_DWORD (__attribute__((stdcall)) *PFN_WlanQueryInterface)(WLAN_HANDLE, const WLAN_GUID *, WLAN_DWORD, void *, WLAN_DWORD *, void **, WLAN_DWORD *);
typedef void (__attribute__((stdcall)) *PFN_WlanFreeMemory)(void *);
typedef WLAN_DWORD (__attribute__((stdcall)) *PFN_WlanCloseHandle)(WLAN_HANDLE, void *);

#if defined(__i386__)
_Static_assert(sizeof(WLAN_GUID)==16, "WLAN_GUID ABI mismatch");
_Static_assert(sizeof(WLAN_DOT11_SSID)==36, "DOT11_SSID ABI mismatch");
_Static_assert(sizeof(WLAN_INTERFACE_INFO)==532, "WLAN_INTERFACE_INFO ABI mismatch");
_Static_assert(sizeof(WLAN_AVAILABLE_NETWORK)==628, "WLAN_AVAILABLE_NETWORK ABI mismatch");
_Static_assert(sizeof(WLAN_CONNECTION_PARAMETERS)==20, "WLAN_CONNECTION_PARAMETERS ABI mismatch");
#endif

/* XP SP3 supports this API subset, but Wlanapi.dll may be absent unless the
   Wireless LAN API for XP SP2 redistributable is installed. Dynamically load. */
#define HERMESXP_WLAN_API_MIN_VERSION 1
#define HERMESXP_WLAN_LIST_FLAGS 0
#define HERMESXP_WLAN_PROFILE_FLAGS 0
#define HERMESXP_WLAN_BSS_INFRASTRUCTURE 1
#define HERMESXP_WLAN_CONNECTED 1
#define HERMESXP_WLAN_PROFILE_CONNECTION_MODE wlan_connection_mode_profile

#endif
