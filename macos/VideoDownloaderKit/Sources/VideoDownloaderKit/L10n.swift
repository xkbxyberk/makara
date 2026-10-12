import Foundation

/// Every user-facing string of the native app comes from `Resources/Localizable.xcstrings`
/// (the native counterpart of `frontend/src/i18n/tr.ts`).
public func L(_ key: String) -> String {
    Bundle.module.localizedString(forKey: key, value: "⟦\(key)⟧", table: nil)
}

/// The numbers in these messages are ports, exit codes and seconds: never digit-grouped
/// (a Turkish locale would print port 8787 as "8.787").
public func L(_ key: String, _ arguments: CVarArg...) -> String {
    String(format: L(key), arguments: arguments)
}
