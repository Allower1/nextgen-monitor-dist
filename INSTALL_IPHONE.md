# NEXTGEN Monitor — iPhone install route (€0)

Status: 2026-09-19. Target device: iOS 26.4.1.

## What is already automated

- Native Swift/SwiftUI source is in this repository under `ios/`.
- GitHub Actions builds it on a standard public macOS runner with Xcode.
- The build is a real unsigned `iphoneos` `.app` packaged as `.ipa` (`arm64`), bundle ID `com.nextgen.monitor`.
- A successful build automatically publishes the IPA into `releases/` and updates `source.json`.
- No Apple Account password, developer certificate, monitor API token, or exchange credential is stored in this repository or CI.

## Why one bootstrap step remains on iOS 26.4.1

SideStore requires a pairing record to communicate with the device. Its official initial install uses a computer/USB pairing. iOS 27 adds device-initiated Wi-Fi pairing, but iOS 26.4.1 cannot create that initial pairing record over Wi-Fi from a remote VPS.

Therefore, on iOS 26.4.1, the only remaining non-automatable action is a one-time physical USB pairing with any compatible borrowed Windows/macOS/Linux computer or supported Chromebook. Ownership of a Mac is not required.

## One-time physical bootstrap

1. Install LocalDevVPN on the iPhone from the App Store.
2. On any compatible borrowed computer, install SideStore's official iLoader only from the official SideStore documentation/source.
3. Connect the iPhone by USB, unlock it, and tap **Trust** on the iPhone.
4. In iLoader select the iPhone and install current SideStore.
5. On iPhone, complete **VPN & Device Management** trust and enable **Developer Mode** when requested.
6. Connect LocalDevVPN, open SideStore, and sign in with your own Apple Account. The Apple Account password must never be entered into NEXTGEN, this repository, the VPS, or a web-signing service.
7. Refresh SideStore once so it shows a fresh 7-day period.

## Install NEXTGEN Monitor

Add this AltSource to SideStore:

`https://raw.githubusercontent.com/Allower1/nextgen-monitor-dist/main/source.json`

One-click URL-scheme form after SideStore is installed:

`sidestore://source?url=https%3A%2F%2Fraw.githubusercontent.com%2FAllower1%2Fnextgen-monitor-dist%2Fmain%2Fsource.json`

Open the NEXTGEN Monitor entry and tap Install. SideStore downloads the unsigned IPA and signs/provisions it with the iPhone owner's free Apple Personal Team before installation.

## Connect to NEXTGEN

1. Install Tailscale on the iPhone and sign it into the same tailnet as the VPS.
2. NEXTGEN Monitor defaults to the private endpoint `http://100.107.22.92:4100`; it is editable in Settings.
3. Enter the monitor bearer token in NEXTGEN Monitor Settings. The app stores it in iOS Keychain and does not include it in the public source or cache.

The monitor API exposes monitoring plus STATUS/PAUSE/RESUME_STATUS only; the native app is not a live trading execution path.
## Refresh and updates

A free Apple Personal Team provisioning profile expires after 7 days. SideStore periodically refreshes apps in the background. LocalDevVPN and Wi-Fi must be available when SideStore installs, updates, or refreshes apps. Before expiry, opening SideStore and manually tapping the remaining-days counter is the reliable fallback.

New NEXTGEN Monitor builds are published automatically into `source.json`. SideStore discovers source updates; installing a new binary still requires the user to tap Update/Install when SideStore presents it.

## Real limitations

- iOS 26.4.1: first pairing cannot be bootstrapped from the remote VPS alone; one physical USB pairing is required.
- Pairing data can become invalid after an iOS update/reset and can occasionally need replacement.
- Free Personal Team: 7-day provisioning profiles, up to 3 installed free-provisioned apps per device (SideStore itself counts), and Apple's other Personal Team limits apply.
- App Store, TestFlight, Ad Hoc distribution and Apple's EU notarized distribution are not zero-cost Personal Team distribution routes.
