# NEXTGEN Monitor native iOS build

This public repository contains only the Swift/SwiftUI monitor client and its unsigned distribution artifacts. It does not contain NEXTGEN trading logic, exchange credentials, Apple credentials, or the monitor API bearer token.

Every change under `ios/` is compiled by a standard GitHub-hosted macOS runner into an unsigned arm64 iPhone `.app`, packaged as `.ipa`, verified, and published into `source.json`. Standard GitHub-hosted runners are free for public repositories.

The IPA is intentionally unsigned. SideStore signs it on the iPhone with the owner’s free Apple Personal Team after the device has completed Apple’s pairing/provisioning bootstrap.
