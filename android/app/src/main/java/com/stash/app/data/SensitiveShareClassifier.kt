package com.stash.app.data

/**
 * A conservative, on-device hint for deciding whether shared text belongs in Vault.
 * This is intentionally a heuristic; apps cannot reliably infer every secret from
 * arbitrary unlabelled text.
 */
object SensitiveShareClassifier {
    data class Classification(val title: String)

    private val password = Regex("\\b(?:password|passwd|passcode|passphrase|pass phrase)\\b", RegexOption.IGNORE_CASE)
    private val verificationCode = Regex("\\b(?:otp|one[ -]?time code|verification code|recovery code|security code)\\b", RegexOption.IGNORE_CASE)
    private val pin = Regex("\\b(?:pin|pin code)\\b", RegexOption.IGNORE_CASE)
    private val privateCredential = Regex(
        "\\b(?:api key|access token|auth(?:entication)? token|bearer token|secret key|private key|seed phrase|recovery phrase|mnemonic)\\b",
        RegexOption.IGNORE_CASE,
    )
    private val financial = Regex(
        "\\b(?:bank details?|bank account|account number|routing number|card number|credit card|debit card|cvv|cvc|iban|ifsc|swift code)\\b",
        RegexOption.IGNORE_CASE,
    )
    private val accountField = Regex(
        "(?:^|\\n)\\s*(?:username|user name|login|email address|account details?)\\s*[:=]\\s*\\S+",
        RegexOption.IGNORE_CASE,
    )
    private val standaloneEmail = Regex("^[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}$", RegexOption.IGNORE_CASE)
    private val standaloneDigits = Regex("^[+\\d][\\d\\s().-]{4,24}$")
    private val apiKeyShape = Regex("\\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\\b")
    private val standalonePasswordShape = Regex("^[^\\s]{14,}$")

    fun classify(text: String): Classification? {
        val content = text.trim()
        if (content.isEmpty()) return null

        return when {
            password.containsMatchIn(content) -> Classification("Shared password")
            verificationCode.containsMatchIn(content) -> Classification("Shared verification code")
            pin.containsMatchIn(content) -> Classification("Shared PIN")
            privateCredential.containsMatchIn(content) || apiKeyShape.containsMatchIn(content) ->
                Classification("Shared private key or token")
            financial.containsMatchIn(content) -> Classification("Shared financial detail")
            accountField.containsMatchIn(content) || standaloneEmail.matches(content) ->
                Classification("Shared account detail")
            standaloneDigits.matches(content) && content.count(Char::isDigit) in 6..24 ->
                Classification("Shared code or account number")
            isPasswordLike(content) -> Classification("Shared password")
            else -> null
        }
    }

    private fun isPasswordLike(content: String): Boolean {
        if (!standalonePasswordShape.matches(content)) return false
        return content.any(Char::isUpperCase) &&
            content.any(Char::isLowerCase) &&
            content.any(Char::isDigit) &&
            content.any { !it.isLetterOrDigit() }
    }
}
