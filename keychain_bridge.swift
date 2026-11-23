import Foundation
import Security
import Darwin

let service = "com.stash.copymaker.local-library-key.v1"
let account = String(getuid())
let command = CommandLine.arguments.dropFirst().first ?? "get"

let query: [String: Any] = [
    kSecClass as String: kSecClassGenericPassword,
    kSecAttrService as String: service,
    kSecAttrAccount as String: account,
]

if command == "get" {
    var lookup = query
    lookup[kSecReturnData as String] = true
    lookup[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    let status = SecItemCopyMatching(lookup as CFDictionary, &result)
    if status == errSecItemNotFound {
        exit(44)
    }
    guard status == errSecSuccess, let data = result as? Data else {
        fputs("Keychain could not read the Stash library key.\n", stderr)
        exit(1)
    }
    print(data.base64EncodedString())
} else if command == "set" {
    let key = FileHandle.standardInput.readDataToEndOfFile()
    guard key.count == 32 else {
        fputs("The Stash library key has an invalid length.\n", stderr)
        exit(2)
    }
    var item = query
    item[kSecValueData as String] = key
    item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    let status = SecItemAdd(item as CFDictionary, nil)
    guard status == errSecSuccess || status == errSecDuplicateItem else {
        fputs("Keychain could not save the Stash library key.\n", stderr)
        exit(1)
    }
    if status == errSecDuplicateItem {
        let updateStatus = SecItemUpdate(query as CFDictionary, [
            kSecValueData as String: key,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ] as CFDictionary)
        guard updateStatus == errSecSuccess else {
            fputs("Keychain could not update the Stash library key.\n", stderr)
            exit(1)
        }
    }
} else {
    fputs("Unsupported Keychain operation.\n", stderr)
    exit(2)
}
