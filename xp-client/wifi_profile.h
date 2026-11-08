#ifndef HERMESXP_WIFI_PROFILE_H
#define HERMESXP_WIFI_PROFILE_H
#include "wlan_api.h"

static int wifi_xml_ascii(WLAN_WCHAR *out, int *pos, int cap, const char *text) {
    int i = 0;
    while (text[i]) {
        if (*pos >= cap - 1) return 0;
        out[(*pos)++] = (WLAN_WCHAR)(unsigned char)text[i++];
    }
    out[*pos] = 0;
    return 1;
}

static int wifi_xml_hex(WLAN_WCHAR *out, int *pos, int cap, const WLAN_DOT11_SSID *ssid) {
    static const char hex[] = "0123456789ABCDEF";
    int i;
    for (i = 0; i < (int)ssid->uSSIDLength; ++i) {
        WLAN_BYTE b = ssid->ucSSID[i];
        if (*pos >= cap - 3) return 0;
        out[(*pos)++] = (WLAN_WCHAR)hex[b >> 4];
        out[(*pos)++] = (WLAN_WCHAR)hex[b & 15];
    }
    out[*pos] = 0;
    return 1;
}

static int wifi_xml_escaped(WLAN_WCHAR *out, int *pos, int cap, const char *text) {
    int i = 0;
    while (text[i]) {
        const char *rep = NULL;
        char one[2];
        if (text[i] == '&') rep = "&amp;";
        else if (text[i] == '<') rep = "&lt;";
        else if (text[i] == '>') rep = "&gt;";
        if (rep) {
            if (!wifi_xml_ascii(out, pos, cap, rep)) return 0;
        } else {
            one[0] = text[i]; one[1] = 0;
            if (!wifi_xml_ascii(out, pos, cap, one)) return 0;
        }
        ++i;
    }
    return 1;
}

static int hermesxp_build_wifi_profile(const WLAN_DOT11_SSID *ssid, int secured,
        WLAN_DWORD auth_id, WLAN_DWORD cipher_id, const char *pass,
        WLAN_WCHAR *profile, int profile_cap, WLAN_WCHAR *xml, int xml_cap) {
    int p = 0, i, pass_len = 0;
    const char *auth = "", *cipher = "";
    if (!ssid || !profile || !xml || !pass || !ssid->uSSIDLength || ssid->uSSIDLength > 32 ||
        profile_cap <= (int)ssid->uSSIDLength || xml_cap < 256) return 0;

    /* XP SP3 derives its profile name from ASCII SSIDs. Reject ambiguous or
       non-ASCII names instead of issuing a connect request for the wrong profile. */
    for (i = 0; i < (int)ssid->uSSIDLength; ++i) {
        WLAN_BYTE c = ssid->ucSSID[i];
        if (c < 32 || c > 126 || c == '&' || c == '<' || c == '>') return 0;
        profile[i] = (WLAN_WCHAR)c;
    }
    profile[ssid->uSSIDLength] = 0;

    if (secured) {
        while (pass[pass_len] && pass_len <= 63) {
            unsigned char c = (unsigned char)pass[pass_len];
            if (c < 32 || c > 126) return 0;
            ++pass_len;
        }
        if (pass_len < 8 || pass_len > 63) return 0;
        if (auth_id == 4) auth = "WPAPSK";
        else if (auth_id == 7) auth = "WPA2PSK";
        else return 0;
        if (cipher_id == 2) cipher = "TKIP";
        else if (cipher_id == 4) cipher = "AES";
        else return 0;
    } else {
        auth = "open";
        cipher = "none";
    }

    if (!wifi_xml_ascii(xml, &p, xml_cap,
        "<WLANProfile xmlns=\"http://www.microsoft.com/networking/WLAN/profile/v1\"><name>")) return 0;
    for (i = 0; profile[i]; ++i) {
        if (p >= xml_cap - 1) return 0;
        xml[p++] = profile[i];
    }
    xml[p] = 0;
    if (!wifi_xml_ascii(xml, &p, xml_cap, "</name><SSIDConfig><SSID><hex>") ||
        !wifi_xml_hex(xml, &p, xml_cap, ssid) ||
        !wifi_xml_ascii(xml, &p, xml_cap, "</hex><name>")) return 0;
    for (i = 0; profile[i]; ++i) {
        if (p >= xml_cap - 1) return 0;
        xml[p++] = profile[i];
    }
    xml[p] = 0;
    if (!wifi_xml_ascii(xml, &p, xml_cap,
        "</name></SSID><nonBroadcast>false</nonBroadcast></SSIDConfig><connectionType>ESS</connectionType><connectionMode>manual</connectionMode><MSM><security><authEncryption><authentication>") ||
        !wifi_xml_ascii(xml, &p, xml_cap, auth) ||
        !wifi_xml_ascii(xml, &p, xml_cap, "</authentication><encryption>") ||
        !wifi_xml_ascii(xml, &p, xml_cap, cipher) ||
        !wifi_xml_ascii(xml, &p, xml_cap, "</encryption><useOneX>false</useOneX></authEncryption>")) return 0;
    if (secured && (!wifi_xml_ascii(xml, &p, xml_cap,
        "<sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>") ||
        !wifi_xml_escaped(xml, &p, xml_cap, pass) ||
        !wifi_xml_ascii(xml, &p, xml_cap, "</keyMaterial></sharedKey>"))) return 0;
    return wifi_xml_ascii(xml, &p, xml_cap, "</security></MSM></WLANProfile>");
}
#endif
