#include <assert.h>
#include <string.h>
#include "../xp-client/wifi_profile.h"

static int wide_contains(const WLAN_WCHAR *haystack, const char *needle) {
    int i, j;
    for (i = 0; haystack[i]; ++i) {
        for (j = 0; needle[j] && haystack[i + j] == (WLAN_WCHAR)(unsigned char)needle[j]; ++j) {}
        if (!needle[j]) return 1;
    }
    return 0;
}

int main(void) {
    WLAN_DOT11_SSID ssid = {7, {'S','a','f','e','N','e','t'}};
    WLAN_WCHAR profile[80], xml[2048];
    assert(hermesxp_build_wifi_profile(&ssid, 1, 7, 4, "sec&ret<key>99", profile, 80, xml, 2048));
    assert(wide_contains(profile, "SafeNet"));
    assert(wide_contains(xml, "<hex>536166654E6574</hex>"));
    assert(wide_contains(xml, "<authentication>WPA2PSK</authentication>"));
    assert(wide_contains(xml, "<encryption>AES</encryption>"));
    assert(wide_contains(xml, "sec&amp;ret&lt;key&gt;99"));
    assert(!wide_contains(xml, "sec&ret<key>99"));

    assert(hermesxp_build_wifi_profile(&ssid, 0, 1, 0, "", profile, 80, xml, 2048));
    assert(wide_contains(xml, "<authentication>open</authentication>"));
    assert(!wide_contains(xml, "<sharedKey>"));

    ssid.ucSSID[0] = 0xE9;
    assert(!hermesxp_build_wifi_profile(&ssid, 0, 1, 0, "", profile, 80, xml, 2048));
    ssid.ucSSID[0] = 'S';
    assert(!hermesxp_build_wifi_profile(&ssid, 1, 3, 4, "password", profile, 80, xml, 2048));
    return 0;
}
