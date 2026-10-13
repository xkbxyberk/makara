import Foundation

/// Every user-facing string of the app comes from `Resources/Localizable.xcstrings` (Turkish;
/// the backend only returns codes).
public func L(_ key: String) -> String {
    Bundle.module.localizedString(forKey: key, value: "⟦\(key)⟧", table: nil)
}

/// The numbers in these messages are ports, exit codes and seconds: never digit-grouped
/// (a Turkish locale would print port 8787 as "8.787").
public func L(_ key: String, _ arguments: CVarArg...) -> String {
    String(format: L(key), arguments: arguments)
}

/// The translation of `key`, or nil when the catalog has none (a code from a newer backend).
public func localizedIfPresent(_ key: String) -> String? {
    let missing = "\u{0}missing"
    let value = Bundle.module.localizedString(forKey: key, value: missing, table: nil)
    return value == missing ? nil : value
}
