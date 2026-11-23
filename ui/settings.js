(() => {
    const settingsButton = document.getElementById("settingsButton");
    const dialog = document.getElementById("settingsDialog");
    const closeButton = document.getElementById("closeSettingsDialog");
    const connectButton = document.getElementById("settingsConnectGoogle");
    const checkButton = document.getElementById("checkStorageButton");
    const uploadButton = document.getElementById("uploadCloudFilesButton");
    const filePicker = document.getElementById("cloudStorageFilePicker");
    const fileList = document.getElementById("cloudFileList");
    const storageText = document.getElementById("settingsStorageText");
    const storageFill = document.getElementById("settingsStorageUsed");
    const storageBar = document.querySelector(".settings-storage-bar");
    const storageStatus = document.getElementById("settingsStorageStatus");
    const accountStatus = document.getElementById("settingsAccountStatus");
    const accountAvatar = document.getElementById("settingsAccountAvatar");
    const globalStatus = document.getElementById("settingsGlobalStatus");
    const sidebarStorageText = document.getElementById("storageText");
    const sidebarStorageUsed = document.getElementById("storageUsed");
    const sidebarStoragePlan = document.getElementById("storagePlanText");
    const phoneClipboardToggle = document.getElementById("togglePhoneClipboardCapture");
    const phoneClipboardPasteButton = document.getElementById("pasteLatestPhoneClipboard");
    const phoneClipboardQuickButton = document.getElementById("pastePhoneClipboardButton");
    const phoneClipboardManualInput = document.getElementById("phoneClipboardManualInput");
    const phoneClipboardManualSave = document.getElementById("saveManualPhoneClipboard");
    const phoneClipboardStatus = document.getElementById("phoneClipboardStatus");
    const phoneClipboardToast = document.getElementById("phoneClipboardToast");
    const localExtensionCodeButton = document.getElementById("createLocalExtensionCode");
    const localExtensionCopyButton = document.getElementById("copyLocalExtensionCode");
    const localExtensionCode = document.getElementById("localExtensionCode");
    const localExtensionStatus = document.getElementById("localExtensionStatus");
    const deviceTransferCodeButton = document.getElementById("createDeviceTransferCode");
    const deviceTransferCopyButton = document.getElementById("copyDeviceTransferDetails");
    const deviceTransferDetails = document.getElementById("deviceTransferReceiveDetails");
    const deviceTransferAddress = document.getElementById("deviceTransferReceiveAddress");
    const deviceTransferCode = document.getElementById("deviceTransferReceiveCode");
    const deviceTransferStatus = document.getElementById("deviceTransferReceiveStatus");
    const mobileCompanionCodeButton = document.getElementById("createMobileCompanionCode");
    const mobileCompanionDetails = document.getElementById("mobileCompanionPairingDetails");
    const mobileCompanionAddress = document.getElementById("mobileCompanionAddress");
    const mobileCompanionCode = document.getElementById("mobileCompanionCode");
    const mobileCompanionStatus = document.getElementById("mobileCompanionStatus");
    const desktopFollowUps = document.getElementById("desktopFollowUps");
    const revokeMobileCompanionButton = document.getElementById("revokeMobileCompanionPairing");
    const browserVideoCopyToggle = document.getElementById("toggleBrowserVideoCopy");
    const browserVideoCopyStatus = document.getElementById("browserVideoCopyStatus");
    const workspaceModesStatus = document.getElementById("workspaceModesStatus");
    const workspaceModeButtons = Array.from(document.querySelectorAll(".smart-mode-toggle"));
    const stashCaptureToggle = document.getElementById("toggleStashCapture");
    const stashCaptureStatus = document.getElementById("stashCaptureStatus");
    const stashRetentionSelect = document.getElementById("stashRetentionDays");
    const stashRetentionStatus = document.getElementById("stashRetentionStatus");
    const stashEncryptionStatus = document.getElementById("stashEncryptionStatus");
    const stashSharingStatus = document.getElementById("stashSharingStatus");
    const excludedAppsInput = document.getElementById("captureExcludedApps");
    const excludedSitesInput = document.getElementById("captureExcludedSites");
    const exclusionSaveButton = document.getElementById("saveCaptureExclusions");
    const exclusionStatus = document.getElementById("captureExclusionsStatus");
    const phoneAccessQr = document.getElementById("phoneAccessQr");
    const phoneAccessStatus = document.getElementById("phoneAccessStatus");
    const phoneAccessLink = document.getElementById("phoneAccessLink");
    const phoneAccessAlternates = document.getElementById("phoneAccessAlternates");
    const phoneAccessAlternateLinks = document.getElementById("phoneAccessAlternateLinks");
    const refreshPhoneAccessButton = document.getElementById("refreshPhoneAccess");
    const settingsSearch = document.getElementById("settingsSearch");
    const settingsSearchStatus = document.getElementById("settingsSearchStatus");
    const securitySessionList = document.getElementById("securitySessionList");
    const securitySessionsStatus = document.getElementById("securitySessionsStatus");
    const twoFactorStatus = document.getElementById("twoFactorStatus");
    const startTwoFactorSetupButton = document.getElementById("startTwoFactorSetup");
    const twoFactorSetupPanel = document.getElementById("twoFactorSetupPanel");
    const twoFactorQr = document.getElementById("twoFactorQr");
    const twoFactorSecret = document.getElementById("twoFactorSecret");
    const twoFactorSetupCode = document.getElementById("twoFactorSetupCode");
    const twoFactorRecoveryPanel = document.getElementById("twoFactorRecoveryPanel");
    const twoFactorRecoveryCodes = document.getElementById("twoFactorRecoveryCodes");
    const twoFactorDisablePanel = document.getElementById("twoFactorDisablePanel");
    const twoFactorDisableCode = document.getElementById("twoFactorDisableCode");
    const remoteSecurityStatus = document.getElementById("remoteSecurityStatus");
    const backupPassword = document.getElementById("backupPassword");
    const backupPasswordConfirm = document.getElementById("backupPasswordConfirm");
    const backupSecurityStatus = document.getElementById("backupSecurityStatus");

    if (!settingsButton || !dialog) return;

    const limitBytes = 2 * 1024 * 1024 * 1024;
    const phoneClipboardPreferenceKey = "stashPhoneClipboardAutoCapture";
    let storageReady = false;
    let phoneClipboardAutoCaptureActive = false;
    let phoneClipboardReadInProgress = false;
    let phoneClipboardToastTimer = 0;
    let browserVideoCopyEnabled = false;
    let workspaceModes = { developer: true, editor: true, student: true };
    let captureEnabled = true;
    let retentionDays = 0;
    let privacySettingsReady = false;
    const settingsDisclosureInitialState = new Map(
        Array.from(dialog.querySelectorAll(".settings-disclosure"), disclosure => [disclosure, disclosure.open])
    );

    function drawPhoneAccessQr(url) {
        if (!phoneAccessQr || !window.StashQRCode) {
            throw new Error("Stash could not create the QR code. Refresh this page and try again.");
        }
        const qr = window.StashQRCode.QrCode.encodeText(url, window.StashQRCode.Ecc.MEDIUM);
        const modules = qr.getModules();
        const quietZone = 4;
        const moduleCount = modules.length + quietZone * 2;
        const scale = phoneAccessQr.width / moduleCount;
        const context = phoneAccessQr.getContext("2d");
        context.fillStyle = "#fff";
        context.fillRect(0, 0, phoneAccessQr.width, phoneAccessQr.height);
        context.fillStyle = "#111";
        modules.forEach((row, y) => row.forEach((dark, x) => {
            if (dark) {
                context.fillRect(
                    Math.floor((x + quietZone) * scale),
                    Math.floor((y + quietZone) * scale),
                    Math.ceil(scale),
                    Math.ceil(scale)
                );
            }
        }));
        phoneAccessQr.hidden = false;
        phoneAccessQr.setAttribute("aria-label", `QR code that opens ${url}`);
    }

    function drawSecurityQr(canvas, value) {
        if (!canvas || !window.StashQRCode) throw new Error("Stash could not create the authenticator QR code.");
        const qr = window.StashQRCode.QrCode.encodeText(value, window.StashQRCode.Ecc.MEDIUM);
        const modules = qr.getModules();
        const quietZone = 4;
        const scale = canvas.width / (modules.length + quietZone * 2);
        const context = canvas.getContext("2d");
        context.fillStyle = "#fff";
        context.fillRect(0, 0, canvas.width, canvas.height);
        context.fillStyle = "#111";
        modules.forEach((row, y) => row.forEach((dark, x) => {
            if (dark) context.fillRect(
                Math.floor((x + quietZone) * scale),
                Math.floor((y + quietZone) * scale),
                Math.ceil(scale),
                Math.ceil(scale),
            );
        }));
    }

    async function refreshSecuritySettings() {
        if (!securitySessionList) return;
        setStatus(securitySessionsStatus, "Loading connected devices…");
        try {
            const [sessionsResponse, authResponse, networkResponse] = await Promise.all([
                fetch("/api/auth/sessions", { cache: "no-store" }),
                fetch("/api/auth/status", { cache: "no-store" }),
                fetch("/api/security/status", { cache: "no-store" }),
            ]);
            const [sessions, auth, network] = await Promise.all([
                sessionsResponse.json().catch(() => ({})),
                authResponse.json().catch(() => ({})),
                networkResponse.json().catch(() => ({})),
            ]);
            if (!sessionsResponse.ok) throw new Error(sessions.error || "Stash could not list connected devices.");
            renderSecuritySessions(sessions.sessions || []);
            renderTwoFactorStatus(auth.two_factor_enabled === true);
            if (remoteSecurityStatus) {
                remoteSecurityStatus.textContent = network.trusted_proxy_configured
                    ? "Remote requests are accepted only through the configured trusted HTTPS proxy. Direct public connections are blocked."
                    : "Local-only mode is active. Direct public-internet connections are blocked; Stash is reachable from this Mac and its private Wi-Fi network.";
            }
        } catch (error) {
            setStatus(securitySessionsStatus, error.message || "Stash could not load security settings.", "error");
        }
    }

    function renderSecuritySessions(sessions) {
        if (!securitySessionList) return;
        securitySessionList.replaceChildren();
        if (!sessions.length) {
            setStatus(securitySessionsStatus, "No connected devices were found. This browser session will appear here after you sign in again.");
            return;
        }
        setStatus(securitySessionsStatus, `${sessions.length} connected device${sessions.length === 1 ? "" : "s"}.`);
        sessions.forEach(item => {
            const row = document.createElement("article");
            row.className = "security-session-row";
            const details = document.createElement("div");
            details.className = "security-session-details";
            const name = document.createElement("strong");
            name.textContent = `${item.device || (item.type === "extension" ? "Copy with Stash extension" : "Browser")} · ${item.current ? "This device" : item.type === "extension" ? "Extension" : "Signed in"}`;
            const activity = document.createElement("small");
            const lastUsed = Number(item.last_seen_at) > 0
                ? new Date(Number(item.last_seen_at) * 1000).toLocaleString()
                : "Unknown";
            activity.textContent = `Last active ${lastUsed}`;
            details.append(name, activity);
            const revoke = document.createElement("button");
            revoke.className = "settings-danger-button";
            revoke.type = "button";
            revoke.textContent = "Revoke";
            revoke.addEventListener("click", () => revokeSecuritySession(item.id));
            row.append(details, revoke);
            securitySessionList.append(row);
        });
    }

    function renderTwoFactorStatus(enabled) {
        if (twoFactorStatus) {
            twoFactorStatus.textContent = enabled
                ? "Two-step verification is on. Keep your recovery codes somewhere safe."
                : "Two-step verification is off. Add an authenticator app for an extra sign-in check.";
        }
        if (startTwoFactorSetupButton) startTwoFactorSetupButton.hidden = enabled;
        if (twoFactorDisablePanel) twoFactorDisablePanel.hidden = !enabled;
    }

    async function revokeSecuritySession(id) {
        try {
            const response = await fetch("/api/auth/sessions/revoke", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ id }),
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "Stash could not revoke that device.");
            if (result.signed_out_current) {
                window.location.reload();
                return;
            }
            setStatus(securitySessionsStatus, "Device access revoked.", "success");
            await refreshSecuritySettings();
        } catch (error) {
            setStatus(securitySessionsStatus, error.message || "Stash could not revoke that device.", "error");
        }
    }

    async function revokeOtherSecuritySessions() {
        const button = document.getElementById("revokeOtherSessions");
        button.disabled = true;
        try {
            const response = await fetch("/api/auth/sessions/revoke-others", { method: "POST" });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "Stash could not sign out the other devices.");
            setStatus(securitySessionsStatus, `${result.revoked || 0} other device${result.revoked === 1 ? "" : "s"} signed out.`, "success");
            await refreshSecuritySettings();
        } catch (error) {
            setStatus(securitySessionsStatus, error.message || "Stash could not sign out the other devices.", "error");
        } finally {
            button.disabled = false;
        }
    }

    async function startTwoFactorSetup() {
        startTwoFactorSetupButton.disabled = true;
        if (twoFactorRecoveryPanel) twoFactorRecoveryPanel.hidden = true;
        try {
            const response = await fetch("/api/auth/two-factor/setup", { method: "POST" });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "Stash could not start authenticator setup.");
            drawSecurityQr(twoFactorQr, result.otpauth_url);
            twoFactorSecret.textContent = result.secret;
            twoFactorSetupPanel.hidden = false;
            twoFactorSetupCode?.focus();
        } catch (error) {
            setStatus(twoFactorStatus, error.message || "Stash could not start authenticator setup.", "error");
        } finally {
            startTwoFactorSetupButton.disabled = false;
        }
    }

    async function confirmTwoFactorSetup() {
        const button = document.getElementById("confirmTwoFactorSetup");
        button.disabled = true;
        try {
            const response = await fetch("/api/auth/two-factor/enable", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code: twoFactorSetupCode?.value || "" }),
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "Stash could not verify that code.");
            twoFactorSetupPanel.hidden = true;
            twoFactorRecoveryCodes.textContent = (result.recovery_codes || []).join("\n");
            twoFactorRecoveryPanel.hidden = false;
            if (twoFactorSetupCode) twoFactorSetupCode.value = "";
            renderTwoFactorStatus(true);
        } catch (error) {
            setStatus(twoFactorStatus, error.message || "Stash could not verify that code.", "error");
        } finally {
            button.disabled = false;
        }
    }

    async function disableTwoFactor() {
        const button = document.getElementById("disableTwoFactor");
        button.disabled = true;
        try {
            const response = await fetch("/api/auth/two-factor/disable", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code: twoFactorDisableCode?.value || "" }),
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "Stash could not turn off two-step verification.");
            if (twoFactorDisableCode) twoFactorDisableCode.value = "";
            if (twoFactorRecoveryPanel) twoFactorRecoveryPanel.hidden = true;
            if (twoFactorRecoveryCodes) twoFactorRecoveryCodes.textContent = "";
            renderTwoFactorStatus(false);
            setStatus(twoFactorStatus, "Two-step verification is off.", "success");
        } catch (error) {
            setStatus(twoFactorStatus, error.message || "Stash could not turn off two-step verification.", "error");
        } finally {
            button.disabled = false;
        }
    }

    async function createEncryptedBackup() {
        const button = document.getElementById("createEncryptedBackup");
        const password = backupPassword?.value || "";
        if (password.length < 12) {
            setStatus(backupSecurityStatus, "Choose a backup password with at least 12 characters.", "error");
            return;
        }
        if (password !== (backupPasswordConfirm?.value || "")) {
            setStatus(backupSecurityStatus, "The backup passwords do not match.", "error");
            return;
        }
        button.disabled = true;
        setStatus(backupSecurityStatus, "Encrypting your Stash library… Keep Stash open until the download starts.");
        try {
            const response = await fetch("/api/security/backup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ password }),
            });
            if (!response.ok) {
                const result = await response.json().catch(() => ({}));
                throw new Error(result.error || "Stash could not create the backup.");
            }
            const blob = await response.blob();
            const objectUrl = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = objectUrl;
            link.download = `Stash-backup-${new Date().toISOString().slice(0, 10)}.stashbackup`;
            document.body.append(link);
            link.click();
            link.remove();
            window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
            if (backupPassword) backupPassword.value = "";
            if (backupPasswordConfirm) backupPasswordConfirm.value = "";
            setStatus(backupSecurityStatus, "Encrypted backup created. Store it and its password separately.", "success");
        } catch (error) {
            setStatus(backupSecurityStatus, error.message || "Stash could not create the backup.", "error");
        } finally {
            button.disabled = false;
        }
    }

    async function restoreEncryptedBackup() {
        const button = document.getElementById("restoreEncryptedBackup");
        const file = document.getElementById("restoreBackupFile")?.files?.[0];
        const password = document.getElementById("restoreBackupPassword")?.value || "";
        if (!file || !password) {
            setStatus(backupSecurityStatus, "Choose a backup file and enter its password.", "error");
            return;
        }
        if (!window.confirm("Restoring replaces the current Stash library on the next restart and signs out every device. Continue?")) return;
        button.disabled = true;
        setStatus(backupSecurityStatus, "Checking and preparing the encrypted backup… This may take a while.");
        try {
            const form = new FormData();
            form.append("backup", file, file.name);
            form.append("password", password);
            const response = await fetch("/api/security/backup/restore", { method: "POST", body: form });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "Stash could not prepare this restore.");
            const restorePassword = document.getElementById("restoreBackupPassword");
            if (restorePassword) restorePassword.value = "";
            setStatus(backupSecurityStatus, "Restore prepared. Quit Stash, then start it again to replace the library. Sign in again after it restarts.", "success");
        } catch (error) {
            setStatus(backupSecurityStatus, error.message || "Stash could not prepare this restore.", "error");
        } finally {
            button.disabled = false;
        }
    }

    async function refreshPhoneAccessLink() {
        if (!phoneAccessStatus) return;
        refreshPhoneAccessButton.disabled = true;
        phoneAccessQr.hidden = true;
        phoneAccessLink.hidden = true;
        if (phoneAccessAlternates) phoneAccessAlternates.hidden = true;
        if (phoneAccessAlternateLinks) phoneAccessAlternateLinks.replaceChildren();
        setStatus(phoneAccessStatus, "Finding this Mac’s private Wi-Fi address…");
        try {
            const response = await fetch("/api/local-network/addresses", { cache: "no-store" });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || !result.url) {
                throw new Error(result.error || "Stash could not find this Mac’s Wi-Fi address.");
            }
            drawPhoneAccessQr(result.url);
            phoneAccessLink.href = result.url;
            phoneAccessLink.textContent = result.url;
            phoneAccessLink.hidden = false;
            const alternateUrls = Array.isArray(result.urls)
                ? result.urls.filter(url => typeof url === "string" && url !== result.url)
                : [];
            if (alternateUrls.length && phoneAccessAlternates && phoneAccessAlternateLinks) {
                alternateUrls.forEach(url => {
                    const link = document.createElement("a");
                    link.href = url;
                    link.textContent = url;
                    phoneAccessAlternateLinks.append(link);
                });
                phoneAccessAlternates.hidden = false;
            }
            setStatus(phoneAccessStatus, "Scan with your phone camera, then sign in to Stash.", "success");
        } catch (error) {
            setStatus(phoneAccessStatus, error.message || "Stash could not create the phone link.", "error");
        } finally {
            refreshPhoneAccessButton.disabled = false;
        }
    }

    function filterSettings() {
        if (!settingsSearch) return;
        const query = settingsSearch.value.trim().toLocaleLowerCase();
        const card = dialog.querySelector(".settings-card");
        const groups = Array.from(card.children).filter(element =>
            element.matches(".settings-section, .settings-disclosure")
        );
        let matchingSections = 0;
        groups.forEach(group => {
            if (group.matches(".settings-disclosure")) {
                const sections = Array.from(group.querySelectorAll(":scope > .settings-section"));
                const summary = group.querySelector(":scope > summary");
                const summaryText = summary?.textContent.toLocaleLowerCase() || "";
                const summaryMatches = Boolean(query && summaryText.includes(query));
                const matches = sections.map(section => {
                    const sectionText = `${summaryText} ${section.textContent}`.toLocaleLowerCase();
                    return !query || summaryMatches || sectionText.includes(query);
                });
                sections.forEach((section, index) => { section.hidden = !matches[index]; });
                const visible = matches.some(Boolean);
                group.hidden = !visible;
                if (query && visible) {
                    group.open = true;
                } else if (!query) {
                    group.open = settingsDisclosureInitialState.get(group) === true;
                }
                matchingSections += matches.filter(Boolean).length;
                return;
            }
            const visible = !query || group.textContent.toLocaleLowerCase().includes(query);
            group.hidden = !visible;
            if (visible) matchingSections += 1;
        });
        if (settingsSearchStatus) {
            settingsSearchStatus.textContent = query
                ? (matchingSections ? `${matchingSections} matching setting section${matchingSections === 1 ? "" : "s"}.` : "No matching settings.")
                : "";
        }
    }

    function renderPrivacySettings(value) {
        privacySettingsReady = true;
        captureEnabled = value?.capture_enabled !== false;
        retentionDays = Number(value?.retention_days) || 0;
        if (excludedAppsInput && document.activeElement !== excludedAppsInput) {
            excludedAppsInput.value = (value?.excluded_app_bundle_ids || []).join("\n");
        }
        if (excludedSitesInput && document.activeElement !== excludedSitesInput) {
            excludedSitesInput.value = (value?.excluded_sites || []).join("\n");
        }
        stashCaptureToggle.disabled = false;
        stashCaptureToggle.setAttribute("aria-pressed", String(captureEnabled));
        stashCaptureToggle.textContent = captureEnabled ? "Pause all capture" : "Resume capture";
        setStatus(stashCaptureStatus, captureEnabled
            ? "Capture is on. Pause it to stop desktop, phone, and browser copies from being saved."
            : "Capture is paused. New desktop, phone, and browser copies are not saved.");
        stashRetentionSelect.value = String(retentionDays);
        stashRetentionSelect.disabled = false;
        setStatus(stashRetentionStatus, retentionDays
            ? `Stash permanently deletes copies after ${retentionDays === 365 ? "1 year" : `${retentionDays} ${retentionDays === 1 ? "day" : "days"}`}.`
            : "Copies are kept until you delete them.");
        if (stashEncryptionStatus) {
            stashEncryptionStatus.textContent = value?.library_encryption === "mac_keychain"
                ? "Local Stash text and saved media are encrypted on this Mac. The library key stays in macOS Keychain. Files you send to another app are decrypted temporarily and removed automatically."
                : "Local library encryption is unavailable. Stash could not confirm access to the macOS Keychain.";
        }
        if (!captureEnabled) {
            if (phoneClipboardAutoCaptureActive) {
                phoneClipboardAutoCaptureActive = false;
                window.removeEventListener("clipboardchange", handlePhoneClipboardChange);
                updatePhoneClipboardToggle();
            }
            window.localStorage.removeItem(phoneClipboardPreferenceKey);
            if (phoneClipboardManualInput) phoneClipboardManualInput.value = "";
            setStatus(phoneClipboardStatus, "Stash capture is paused. Phone clipboard capture is off.");
        }
        if (stashSharingStatus) {
            stashSharingStatus.textContent = value?.shared_mode
                ? (value.shared_registration_open
                    ? "Shared Stash is enabled and new account registration is open. Close registration on the server when you no longer need it."
                    : "Shared Stash is enabled. New account registration is closed; existing accounts can still sign in.")
                : "Remote Shared Stash is off unless it is explicitly enabled by the server owner. New shared accounts are closed by default.";
        }
    }

    async function refreshPrivacySettings() {
        if (!stashCaptureToggle || !stashRetentionSelect) return;
        stashCaptureToggle.disabled = true;
        stashRetentionSelect.disabled = true;
        setStatus(stashCaptureStatus, "Checking capture status…");
        try {
            const response = await fetch("/api/settings/privacy", { cache: "no-store" });
            const value = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(value.error || "Stash could not read these privacy settings.");
            renderPrivacySettings(value);
        } catch (error) {
            setStatus(stashCaptureStatus, error.message || "Stash could not read these privacy settings.", "error");
        }
    }

    async function savePrivacySetting(changes) {
        const response = await fetch("/api/settings/privacy", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(changes),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.error || "Stash could not save this privacy setting.");
        return result;
    }

    function parseExclusionLines(value) {
        return Array.from(new Set(String(value || "")
            .split(/[\n,]/)
            .map(item => item.trim())
            .filter(Boolean)));
    }

    async function saveCaptureExclusions() {
        exclusionSaveButton.disabled = true;
        setStatus(exclusionStatus, "Saving exclusions…");
        try {
            const result = await savePrivacySetting({
                excluded_app_bundle_ids: parseExclusionLines(excludedAppsInput.value),
                excluded_sites: parseExclusionLines(excludedSitesInput.value),
            });
            renderPrivacySettings(result);
            setStatus(exclusionStatus, "Capture exclusions saved.", "success");
        } catch (error) {
            setStatus(exclusionStatus, error.message || "Stash could not save these exclusions.", "error");
        } finally {
            exclusionSaveButton.disabled = false;
        }
    }

    async function toggleStashCapture() {
        stashCaptureToggle.disabled = true;
        setStatus(stashCaptureStatus, "Saving capture setting…");
        try {
            const result = await savePrivacySetting({ capture_enabled: !captureEnabled });
            renderPrivacySettings({ capture_enabled: result.capture_enabled, retention_days: retentionDays });
            setStatus(stashCaptureStatus, result.capture_enabled
                ? "Capture is on. Pause it to stop desktop, phone, and browser copies from being saved."
                : "Capture is paused. New desktop, phone, and browser copies are not saved.", "success");
        } catch (error) {
            setStatus(stashCaptureStatus, error.message || "Stash could not save this setting.", "error");
            stashCaptureToggle.disabled = false;
        }
    }

    async function changeStashRetention() {
        const chosenDays = Number(stashRetentionSelect.value);
        stashRetentionSelect.disabled = true;
        setStatus(stashRetentionStatus, "Saving retention setting…");
        try {
            const result = await savePrivacySetting({ retention_days: chosenDays });
            retentionDays = Number(result.retention_days) || 0;
            stashRetentionSelect.value = String(retentionDays);
            setStatus(stashRetentionStatus, result.removed_count
                ? `Setting saved. Stash permanently deleted ${result.removed_count} expired ${result.removed_count === 1 ? "copy" : "copies"}.`
                : retentionDays
                    ? `Stash will permanently delete copies after ${retentionDays === 365 ? "1 year" : `${retentionDays} ${retentionDays === 1 ? "day" : "days"}`}.`
                    : "Copies are kept until you delete them.",
                "success");
        } catch (error) {
            stashRetentionSelect.value = String(retentionDays);
            setStatus(stashRetentionStatus, error.message || "Stash could not save this setting.", "error");
        } finally {
            stashRetentionSelect.disabled = false;
        }
    }

    function formatBytes(bytes) {
        const value = Number(bytes) || 0;
        if (value >= 1024 ** 3) return `${(value / (1024 ** 3)).toFixed(2)} GB`;
        if (value >= 1024 ** 2) return `${(value / (1024 ** 2)).toFixed(1)} MB`;
        if (value >= 1024) return `${(value / 1024).toFixed(0)} KB`;
        return `${value} B`;
    }

    function setStatus(element, message, kind = "") {
        if (!element) return;
        element.textContent = message;
        if (kind) element.dataset.kind = kind;
        else delete element.dataset.kind;
    }

    function renderBrowserVideoCopySetting(enabled) {
        browserVideoCopyEnabled = Boolean(enabled);
        browserVideoCopyToggle.setAttribute("aria-pressed", String(browserVideoCopyEnabled));
        browserVideoCopyToggle.textContent = browserVideoCopyEnabled
            ? "Block video copying"
            : "Allow video copying";
        setStatus(browserVideoCopyStatus, browserVideoCopyEnabled
            ? "Allowed. Copy with Stash can save browser videos into this library."
            : "Off. The extension will not copy browser videos until you allow it here.");
    }

    async function refreshBrowserVideoCopySetting() {
        if (!browserVideoCopyToggle) return;
        browserVideoCopyToggle.disabled = true;
        setStatus(browserVideoCopyStatus, "Checking video-copy permission…");
        try {
            const response = await fetch("/api/settings/browser-video-copy", { cache: "no-store" });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "Stash could not read this setting.");
            renderBrowserVideoCopySetting(result.enabled === true);
        } catch (error) {
            setStatus(browserVideoCopyStatus, error.message || "Stash could not read this setting.", "error");
            browserVideoCopyToggle.textContent = "Permission unavailable";
        } finally {
            browserVideoCopyToggle.disabled = false;
        }
    }

    async function toggleBrowserVideoCopySetting() {
        if (!browserVideoCopyToggle) return;
        browserVideoCopyToggle.disabled = true;
        setStatus(browserVideoCopyStatus, "Saving video-copy permission…");
        try {
            const response = await fetch("/api/settings/browser-video-copy", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enabled: !browserVideoCopyEnabled }),
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "Stash could not save this setting.");
            renderBrowserVideoCopySetting(result.enabled === true);
        } catch (error) {
            setStatus(browserVideoCopyStatus, error.message || "Stash could not save this setting.", "error");
        } finally {
            browserVideoCopyToggle.disabled = false;
        }
    }

    function renderWorkspaceModeSettings(modes) {
        workspaceModes = {
            developer: modes?.developer !== false,
            editor: modes?.editor !== false,
            student: modes?.student !== false,
        };
        workspaceModeButtons.forEach(button => {
            const enabled = workspaceModes[button.dataset.smartMode] === true;
            button.disabled = false;
            button.setAttribute("aria-pressed", String(enabled));
            button.textContent = enabled ? "On" : "Off";
            button.classList.toggle("is-enabled", enabled);
        });
    }

    async function refreshWorkspaceModeSettings() {
        if (!workspaceModeButtons.length) return;
        workspaceModeButtons.forEach(button => { button.disabled = true; });
        setStatus(workspaceModesStatus, "Checking smart section settings…");
        try {
            const response = await fetch("/api/settings/workspace-modes", { cache: "no-store" });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "Stash could not load these settings.");
            renderWorkspaceModeSettings(result.modes || {});
            setStatus(workspaceModesStatus, "Off stops automatic sorting for new copies. Copies already in a section stay there.");
        } catch (error) {
            setStatus(workspaceModesStatus, error.message || "Stash could not load these settings.", "error");
            workspaceModeButtons.forEach(button => { button.disabled = true; });
        }
    }

    async function toggleWorkspaceMode(button) {
        const mode = button.dataset.smartMode;
        if (!mode || !(mode in workspaceModes)) return;
        button.disabled = true;
        setStatus(workspaceModesStatus, "Saving smart section setting…");
        try {
            const response = await fetch("/api/settings/workspace-modes", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ mode, enabled: !workspaceModes[mode] }),
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.error || "Stash could not save this setting.");
            renderWorkspaceModeSettings(result.modes || {});
            setStatus(workspaceModesStatus, "Setting saved. This only changes where new copies are sorted.", "success");
        } catch (error) {
            setStatus(workspaceModesStatus, error.message || "Stash could not save this setting.", "error");
            button.disabled = false;
        }
    }

    function phoneClipboardCanRead() {
        return Boolean(
            window.isSecureContext &&
            navigator.clipboard &&
            typeof navigator.clipboard.readText === "function"
        );
    }

    function phoneClipboardCanAutoCapture() {
        return phoneClipboardCanRead() && (
            typeof window.ClipboardChangeEvent === "function" ||
            "onclipboardchange" in window
        );
    }

    function showPhoneClipboardToast(message, kind = "") {
        if (!phoneClipboardToast) return;
        phoneClipboardToast.textContent = message;
        if (kind) phoneClipboardToast.dataset.kind = kind;
        else delete phoneClipboardToast.dataset.kind;
        phoneClipboardToast.hidden = false;
        window.clearTimeout(phoneClipboardToastTimer);
        phoneClipboardToastTimer = window.setTimeout(() => {
            phoneClipboardToast.hidden = true;
        }, 3500);
    }

    function clipboardAccessError(error) {
        if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
            return "The browser blocked clipboard access. Open Settings → Phone clipboard, paste into the box there, then tap Save pasted text.";
        }
        return error?.message || "Stash could not read the phone clipboard.";
    }

    async function savePhoneClipboardText(text) {
        if (typeof text !== "string" || !text.trim()) {
            throw new Error("There is no text to save from the clipboard.");
        }

        const response = await fetch("/api/clipboard/mobile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            if (response.status === 423 && phoneClipboardManualInput) {
                phoneClipboardManualInput.value = "";
            }
            throw new Error(result.error || "Stash could not save this copied text.");
        }

        document.dispatchEvent(new CustomEvent("copy-maker:clipboard-imported"));
        return result.item;
    }

    async function captureCurrentPhoneClipboard(showToast = false) {
        try {
            if (!phoneClipboardCanRead()) {
                throw new Error("Clipboard reading is unavailable in this browser. Paste the text into the box in Settings instead.");
            }

            const text = await navigator.clipboard.readText();
            if (!text.trim()) {
                throw new Error("No copied text was found. Copy text on your phone, then try again.");
            }

            await savePhoneClipboardText(text);
            const message = "Copied text saved to Stash on the Mac.";
            setStatus(phoneClipboardStatus, message, "success");
            if (showToast) showPhoneClipboardToast(message, "success");
            return true;
        } catch (error) {
            const message = clipboardAccessError(error);
            setStatus(phoneClipboardStatus, message, "error");
            if (showToast) showPhoneClipboardToast(message, "error");
            return false;
        }
    }

    function updatePhoneClipboardToggle() {
        if (!phoneClipboardToggle) return;
        phoneClipboardToggle.textContent = phoneClipboardAutoCaptureActive
            ? "Turn off automatic capture"
            : "Enable automatic capture";
        phoneClipboardToggle.setAttribute(
            "aria-pressed",
            String(phoneClipboardAutoCaptureActive)
        );
    }

    function stopPhoneClipboardAutoCapture(showStatus = true) {
        if (!phoneClipboardAutoCaptureActive) return;
        phoneClipboardAutoCaptureActive = false;
        window.removeEventListener("clipboardchange", handlePhoneClipboardChange);
        window.localStorage.removeItem(phoneClipboardPreferenceKey);
        updatePhoneClipboardToggle();
        if (showStatus) {
            setStatus(phoneClipboardStatus, "Automatic clipboard capture is off.");
        }
    }

    async function handlePhoneClipboardChange() {
        if (!phoneClipboardAutoCaptureActive || phoneClipboardReadInProgress) return;
        phoneClipboardReadInProgress = true;
        try {
            const text = await navigator.clipboard.readText();
            if (!text.trim()) return;
            await savePhoneClipboardText(text);
            setStatus(phoneClipboardStatus, "New copied text saved to Stash on the Mac.", "success");
            showPhoneClipboardToast("New copied text saved to Stash.", "success");
        } catch (error) {
            const message = clipboardAccessError(error);
            stopPhoneClipboardAutoCapture(false);
            setStatus(phoneClipboardStatus, `${message} Automatic capture is off.`, "error");
            showPhoneClipboardToast("Automatic capture stopped. Use Paste in Settings.", "error");
        } finally {
            phoneClipboardReadInProgress = false;
        }
    }

    async function enablePhoneClipboardAutoCapture() {
        if (!privacySettingsReady || !captureEnabled) {
            setStatus(phoneClipboardStatus, "Resume Stash capture in Privacy & Safety before enabling phone clipboard capture.", "error");
            return;
        }
        if (!phoneClipboardCanAutoCapture()) {
            setStatus(
                phoneClipboardStatus,
                "This browser cannot watch clipboard changes automatically. Use Paste latest copied text after copying.",
                "error"
            );
            if (revokeMobileCompanionButton) revokeMobileCompanionButton.hidden = !status.paired;
            return;
        }

        phoneClipboardToggle.disabled = true;
        try {
            const currentText = await navigator.clipboard.readText();
            if (currentText.trim()) {
                await savePhoneClipboardText(currentText);
            }
            window.localStorage.setItem(phoneClipboardPreferenceKey, "true");
            phoneClipboardAutoCaptureActive = true;
            window.addEventListener("clipboardchange", handlePhoneClipboardChange);
            updatePhoneClipboardToggle();
            setStatus(
                phoneClipboardStatus,
                currentText.trim()
                    ? "Automatic capture is on. The current copied text was saved; new text will be saved while Stash is open and active."
                    : "Automatic capture is on while Stash is open and active. New copied text will be saved to the Mac.",
                "success"
            );
        } catch (error) {
            setStatus(phoneClipboardStatus, clipboardAccessError(error), "error");
        } finally {
            phoneClipboardToggle.disabled = false;
        }
    }

    function restorePhoneClipboardAutoCapture() {
        if (!privacySettingsReady || !captureEnabled) {
            window.localStorage.removeItem(phoneClipboardPreferenceKey);
            phoneClipboardAutoCaptureActive = false;
            updatePhoneClipboardToggle();
            return;
        }
        if (window.localStorage.getItem(phoneClipboardPreferenceKey) !== "true") {
            if (!phoneClipboardCanAutoCapture()) {
                setStatus(
                    phoneClipboardStatus,
                    "Automatic clipboard monitoring is unavailable in this browser. Use Paste latest copied text after copying."
                );
            }
            return;
        }
        if (!phoneClipboardCanAutoCapture()) {
            window.localStorage.removeItem(phoneClipboardPreferenceKey);
            setStatus(
                phoneClipboardStatus,
                "This browser cannot watch clipboard changes automatically. Use Paste latest copied text after copying."
            );
            return;
        }

        phoneClipboardAutoCaptureActive = true;
        window.addEventListener("clipboardchange", handlePhoneClipboardChange);
        updatePhoneClipboardToggle();
        setStatus(phoneClipboardStatus, "Automatic capture is on while Stash is open and active.");
    }

    function setStorageUsage(usedBytes) {
        const used = Math.max(0, Number(usedBytes) || 0);
        const percent = Math.min(100, (used / limitBytes) * 100);
        if (storageText) storageText.textContent = `${formatBytes(used)} / 2 GB`;
        if (storageFill) storageFill.style.width = `${percent}%`;
        if (storageBar) storageBar.setAttribute("aria-valuenow", String(Math.round(percent)));
        if (sidebarStorageText) sidebarStorageText.textContent = `${formatBytes(used)} / 2 GB`;
        if (sidebarStorageUsed) sidebarStorageUsed.style.width = `${percent}%`;
        if (sidebarStoragePlan) sidebarStoragePlan.textContent = "Firebase demo · 2 GB";
        window.dispatchEvent(new CustomEvent("stash:storage-usage", {
            detail: { usedBytes: used, totalBytes: limitBytes, percent, ready: storageReady },
        }));
    }

    function renderFiles(files) {
        if (!fileList) return;
        fileList.replaceChildren();
        if (!Array.isArray(files) || files.length === 0) {
            const empty = document.createElement("li");
            empty.className = "settings-status";
            empty.textContent = "No files in your cloud library yet.";
            fileList.append(empty);
            return;
        }

        for (const file of files) {
            const row = document.createElement("li");
            row.className = "cloud-file-item";

            const details = document.createElement("div");
            details.style.minWidth = "0";
            const name = document.createElement("div");
            name.className = "cloud-file-name";
            name.textContent = file.displayName || "Cloud file";
            const meta = document.createElement("div");
            meta.className = "cloud-file-meta";
            meta.textContent = `${formatBytes(file.sizeBytes)}${file.createdAt ? ` · ${new Date(file.createdAt).toLocaleDateString()}` : ""}`;
            details.append(name, meta);

            const actions = document.createElement("div");
            actions.className = "cloud-file-actions";

            const appSelect = document.createElement("select");
            appSelect.className = "settings-app-select";
            appSelect.setAttribute("aria-label", `Choose an app for ${file.displayName || "cloud file"}`);
            for (const [value, label] of [["capcut", "CapCut"], ["davinci", "DaVinci"], ["cursor", "Cursor"]]) {
                const option = document.createElement("option");
                option.value = value;
                option.textContent = label;
                appSelect.append(option);
            }

            const prepare = document.createElement("button");
            prepare.className = "settings-secondary-button";
            prepare.type = "button";
            prepare.textContent = "Open in selected app";
            prepare.setAttribute("aria-label", `Open ${file.displayName || "cloud file"} in the selected app`);
            prepare.addEventListener("click", async () => {
                prepare.disabled = true;
                appSelect.disabled = true;
                setStatus(globalStatus, `Preparing ${file.displayName || "cloud file"} for ${appSelect.options[appSelect.selectedIndex].text}…`);
                try {
                    const response = await fetch("/api/cloud-storage/prepare-for-app", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ name: file.name, app: appSelect.value }),
                    });
                    const result = await response.json().catch(() => ({}));
                    if (!response.ok) throw new Error(result.error || "The cloud file could not be prepared.");
                    const labels = { capcut: "CapCut", davinci: "DaVinci Resolve", cursor: "Cursor" };
                    const appLabel = labels[result.app] || "app";
                    const nextStep = result.nextStep || "Import the file from Finder into your project.";
                    setStatus(
                        globalStatus,
                        result.appOpened
                            ? `${appLabel} is open. ${nextStep}`
                            : `The file is selected in Finder. Open ${appLabel} manually. ${nextStep}`,
                        "success"
                    );
                } catch (error) {
                    setStatus(globalStatus, error.message, "error");
                } finally {
                    prepare.disabled = false;
                    appSelect.disabled = false;
                }
            });

            const download = document.createElement("a");
            download.className = "settings-secondary-button";
            download.textContent = "Download";
            download.href = `/api/cloud-storage/download?name=${encodeURIComponent(file.name)}`;
            download.setAttribute("aria-label", `Download ${file.displayName || "cloud file"}`);

            const remove = document.createElement("button");
            remove.className = "settings-danger-button";
            remove.type = "button";
            remove.textContent = "Remove";
            remove.setAttribute("aria-label", `Remove ${file.displayName || "cloud file"}`);
            remove.addEventListener("click", async () => {
                const label = file.displayName || "this file";
                if (!window.confirm(`Permanently remove ${label} from Firebase cloud storage?`)) return;
                remove.disabled = true;
                try {
                    const response = await fetch("/api/cloud-storage/files", {
                        method: "DELETE",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ name: file.name }),
                    });
                    const result = await response.json().catch(() => ({}));
                    if (!response.ok) throw new Error(result.error || "The file could not be removed.");
                    setStorageUsage(result.usedBytes);
                    setStatus(storageStatus, "Cloud file removed.", "success");
                    await refreshCloudStorage();
                } catch (error) {
                    setStatus(storageStatus, error.message, "error");
                    remove.disabled = false;
                }
            });
            actions.append(appSelect, prepare, download, remove);
            row.append(details, actions);
            fileList.append(row);
        }
    }

    async function refreshCloudStorage({ statusOnly = false } = {}) {
        if (checkButton) checkButton.disabled = true;
        if (storageText) storageText.textContent = "Checking…";
        setStatus(storageStatus, "Checking Firebase cloud storage…");

        try {
            const response = await fetch("/api/cloud-storage/status", { cache: "no-store" });
            const status = await response.json().catch(() => ({}));
            storageReady = Boolean(response.ok && status.ready);
            setStorageUsage(status.usedBytes || 0);

            const googleLinked = Boolean(status.linked);
            if (connectButton) connectButton.hidden = googleLinked;
            if (accountStatus) {
                accountStatus.textContent = googleLinked
                    ? "Google sign-in is connected for private cloud storage."
                    : "Your Stash account is active. Connect Google to use Firebase cloud storage.";
            }
            if (accountAvatar) {
                const profile = document.getElementById("logoutButton") || document.getElementById("settingsSignOut");
                accountAvatar.textContent = profile?.dataset.username?.slice(0, 1).toUpperCase() || "S";
            }

            if (!storageReady) {
                renderFiles([]);
                if (uploadButton) uploadButton.disabled = true;
                setStatus(storageStatus, status.error || "Firebase Storage is not ready yet.", "error");
                if (sidebarStoragePlan) sidebarStoragePlan.textContent = googleLinked ? "Firebase setup needed" : "Connect Google";
                return;
            }

            if (statusOnly) return;

            const listResponse = await fetch("/api/cloud-storage/files", { cache: "no-store" });
            const listData = await listResponse.json().catch(() => ({}));
            if (!listResponse.ok) throw new Error(listData.error || "The cloud file list could not be loaded.");
            renderFiles(listData.files);
            setStorageUsage(listData.usedBytes);
            if (uploadButton) uploadButton.disabled = false;
            setStatus(storageStatus, `${listData.files.length} file${listData.files.length === 1 ? "" : "s"} in your private cloud library.`, "success");
        } catch (error) {
            storageReady = false;
            window.dispatchEvent(new CustomEvent("stash:storage-usage", {
                detail: { ready: false },
            }));
            if (uploadButton) uploadButton.disabled = true;
            setStatus(storageStatus, error.message || "Could not check Firebase Storage.", "error");
        } finally {
            if (checkButton) checkButton.disabled = false;
        }
    }

    async function uploadSelectedFiles(files) {
        if (!storageReady || !files?.length) return;
        const selectedNames = files.slice(0, 8).map(file => file.name).join("\n");
        const moreFiles = files.length > 8 ? `\n…and ${files.length - 8} more file${files.length - 8 === 1 ? "" : "s"}` : "";
        if (!window.confirm(
            `Send ${files.length} selected file${files.length === 1 ? "" : "s"} to Firebase cloud storage for this account?\n\n${selectedNames}${moreFiles}`
        )) {
            if (filePicker) filePicker.value = "";
            return;
        }
        if (uploadButton) uploadButton.disabled = true;
        let uploadedCount = 0;
        try {
            for (const file of files) {
                setStatus(storageStatus, `Uploading ${file.name}…`);
                const body = new FormData();
                body.append("file", file, file.name);
                const response = await fetch("/api/cloud-storage/upload", { method: "POST", body });
                const result = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(result.error || `Could not upload ${file.name}.`);
                uploadedCount += 1;
                setStorageUsage(result.usedBytes);
            }
            setStatus(storageStatus, `${uploadedCount} file${uploadedCount === 1 ? "" : "s"} uploaded to Firebase.`, "success");
            await refreshCloudStorage();
        } catch (error) {
            setStatus(storageStatus, error.message, "error");
            await refreshCloudStorage();
        } finally {
            if (uploadButton) uploadButton.disabled = !storageReady;
            if (filePicker) filePicker.value = "";
        }
    }

    async function createLocalExtensionPairingCode() {
        if (!localExtensionCodeButton) return;
        localExtensionCodeButton.disabled = true;
        if (localExtensionCopyButton) localExtensionCopyButton.hidden = true;
        if (localExtensionCode) localExtensionCode.hidden = true;
        setStatus(localExtensionStatus, "Creating a one-time code…");
        try {
            const response = await fetch("/api/auth/local-extension-code", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: "{}",
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || !result.code) {
                throw new Error(result.error || "Stash could not create a pairing code.");
            }
            localExtensionCode.textContent = result.code;
            localExtensionCode.hidden = false;
            if (localExtensionCopyButton) localExtensionCopyButton.hidden = false;
            setStatus(localExtensionStatus, "Enter this once in the Stash extension with http://127.0.0.1:5050. It expires in 10 minutes and replaces the current local extension connection.", "success");
        } catch (error) {
            setStatus(localExtensionStatus, error.message || "Stash could not create a pairing code.", "error");
        } finally {
            localExtensionCodeButton.disabled = false;
        }
    }

    async function copyLocalExtensionPairingCode() {
        const code = localExtensionCode?.textContent || "";
        if (!code) return;
        try {
            await navigator.clipboard.writeText(code);
            setStatus(localExtensionStatus, "Code copied. Paste it into the Stash extension now; it expires in 10 minutes.", "success");
        } catch {
            setStatus(localExtensionStatus, "Select the displayed code and copy it into the Stash extension.", "error");
        }
    }

    async function createDeviceTransferPairingCode() {
        if (!deviceTransferCodeButton) return;
        deviceTransferCodeButton.disabled = true;
        if (deviceTransferCopyButton) deviceTransferCopyButton.hidden = true;
        if (deviceTransferDetails) deviceTransferDetails.hidden = true;
        setStatus(deviceTransferStatus, "Preparing this laptop to receive copies…");
        try {
            const response = await fetch("/api/device-transfer/code", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: "{}",
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || !result.code || !result.address) {
                throw new Error(result.error || "Stash could not create a receive code.");
            }
            const addresses = Array.isArray(result.addresses) && result.addresses.length
                ? result.addresses
                : [result.address];
            deviceTransferAddress.textContent = addresses.join("\n");
            deviceTransferCode.textContent = result.code;
            if (deviceTransferDetails) deviceTransferDetails.hidden = false;
            if (deviceTransferCopyButton) deviceTransferCopyButton.hidden = false;
            setStatus(deviceTransferStatus, "Ready. On the sending laptop, select copies and choose Send to another Stash. This code works once and expires in 10 minutes.", "success");
        } catch (error) {
            setStatus(deviceTransferStatus, error.message || "Stash could not create a receive code.", "error");
        } finally {
            deviceTransferCodeButton.disabled = false;
        }
    }

    async function copyDeviceTransferPairingDetails() {
        const address = deviceTransferAddress?.textContent || "";
        const code = deviceTransferCode?.textContent || "";
        if (!address || !code) return;
        try {
            await navigator.clipboard.writeText(`${address.split("\n")[0]}\n${code}`);
            setStatus(deviceTransferStatus, "Address and code copied. Enter them on the sending laptop before the code expires.", "success");
        } catch {
            setStatus(deviceTransferStatus, "Select the displayed address and code to copy them manually.", "error");
        }
    }

    async function refreshMobileCompanionStatus() {
        if (!mobileCompanionStatus) return;
        try {
            const [statusResponse, followUpsResponse] = await Promise.all([
                fetch("/api/mobile-companion/status", { cache: "no-store" }),
                fetch("/api/mobile-companion/follow-ups", { cache: "no-store" }),
            ]);
            const status = await statusResponse.json().catch(() => ({}));
            const result = await followUpsResponse.json().catch(() => ({}));
            if (!statusResponse.ok || !followUpsResponse.ok) throw new Error("Could not load phone link status.");
            setStatus(
                mobileCompanionStatus,
                status.paired
                    ? "An Android phone is paired. Ava file previews can be reviewed on that phone."
                    : "No Android phone is paired. Create a code, then enter it in Stash on Android.",
                status.paired ? "success" : "",
            );
            if (!desktopFollowUps) return;
            desktopFollowUps.replaceChildren();
            const entries = Array.isArray(result.follow_ups) ? result.follow_ups : [];
            const title = document.createElement("strong");
            title.textContent = entries.length ? `Synced Ava Follow-ups (${entries.length})` : "No synced Ava Follow-ups yet.";
            desktopFollowUps.append(title);
            entries.slice(0, 8).forEach(entry => {
                const row = document.createElement("p");
                const eventDate = Number(entry.eventAt) ? new Date(Number(entry.eventAt)).toLocaleDateString() : "date unavailable";
                const reminderDate = Number(entry.remindAt) ? new Date(Number(entry.remindAt)).toLocaleString() : "reminder time unavailable";
                row.textContent = `${entry.eventLabel || "Follow-up"} · ${entry.sourceTitle || "Saved item"} · ${eventDate} · remind ${reminderDate}`;
                desktopFollowUps.append(row);
            });
            if (entries.length > 8) {
                const more = document.createElement("p");
                more.textContent = `And ${entries.length - 8} more. Open Ava Follow-ups in Stash on Android to manage them.`;
                desktopFollowUps.append(more);
            }
        } catch (error) {
            setStatus(mobileCompanionStatus, error.message || "Could not load the phone link status.", "error");
        }
    }

    async function createMobileCompanionPairingCode() {
        if (!mobileCompanionCodeButton) return;
        mobileCompanionCodeButton.disabled = true;
        if (mobileCompanionDetails) mobileCompanionDetails.hidden = true;
        setStatus(mobileCompanionStatus, "Creating a one-time phone pairing code…");
        try {
            const response = await fetch("/api/mobile-companion/pair-code", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: "{}",
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || !result.code || !Array.isArray(result.addresses) || !result.addresses.length) {
                throw new Error(result.error || "Stash could not create a phone pairing code.");
            }
            mobileCompanionAddress.textContent = result.addresses.join("\n");
            mobileCompanionCode.textContent = result.code;
            if (mobileCompanionDetails) mobileCompanionDetails.hidden = false;
            const replacement = result.replaces_existing_phone ? " This replaces the phone currently paired." : "";
            setStatus(mobileCompanionStatus, `Enter the address and code in Stash on Android now. The code expires in 10 minutes and works once.${replacement}`, "success");
        } catch (error) {
            setStatus(mobileCompanionStatus, error.message || "Stash could not create a phone pairing code.", "error");
        } finally {
            mobileCompanionCodeButton.disabled = false;
        }
    }

    async function revokeMobileCompanionPairing() {
        if (!revokeMobileCompanionButton) return;
        revokeMobileCompanionButton.disabled = true;
        try {
            const response = await fetch("/api/mobile-companion/unpair", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: "{}",
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok || !result.success) throw new Error(result.error || "Could not disconnect the paired phone.");
            setStatus(mobileCompanionStatus, "The paired Android phone has been disconnected.", "success");
            await refreshMobileCompanionStatus();
        } catch (error) {
            setStatus(mobileCompanionStatus, error.message || "Could not disconnect the paired phone.", "error");
        } finally {
            revokeMobileCompanionButton.disabled = false;
        }
    }

    settingsButton.addEventListener("click", () => {
        const profile = document.getElementById("logoutButton") || document.getElementById("settingsSignOut");
        if (accountStatus && profile?.dataset.username) {
            accountStatus.textContent = `Signed in as ${profile.dataset.username}.`;
        }
        if (!dialog.open) dialog.showModal();
        refreshPhoneAccessLink();
        refreshBrowserVideoCopySetting();
        refreshPrivacySettings();
        refreshSecuritySettings();
        refreshWorkspaceModeSettings();
        refreshCloudStorage();
        refreshMobileCompanionStatus();
    });
    browserVideoCopyToggle?.addEventListener("click", toggleBrowserVideoCopySetting);
    stashCaptureToggle?.addEventListener("click", toggleStashCapture);
    stashRetentionSelect?.addEventListener("change", changeStashRetention);
    exclusionSaveButton?.addEventListener("click", saveCaptureExclusions);
    refreshPhoneAccessButton?.addEventListener("click", refreshPhoneAccessLink);
    settingsSearch?.addEventListener("input", filterSettings);
    document.getElementById("refreshSecuritySessions")?.addEventListener("click", refreshSecuritySettings);
    document.getElementById("revokeOtherSessions")?.addEventListener("click", revokeOtherSecuritySessions);
    startTwoFactorSetupButton?.addEventListener("click", startTwoFactorSetup);
    document.getElementById("confirmTwoFactorSetup")?.addEventListener("click", confirmTwoFactorSetup);
    document.getElementById("cancelTwoFactorSetup")?.addEventListener("click", () => {
        if (twoFactorSetupPanel) twoFactorSetupPanel.hidden = true;
        if (twoFactorSetupCode) twoFactorSetupCode.value = "";
    });
    document.getElementById("disableTwoFactor")?.addEventListener("click", disableTwoFactor);
    document.getElementById("copyTwoFactorRecoveryCodes")?.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(twoFactorRecoveryCodes?.textContent || "");
            setStatus(twoFactorStatus, "Recovery codes copied. Store them somewhere safe.", "success");
        } catch {
            setStatus(twoFactorStatus, "Select the recovery codes and copy them somewhere safe.", "error");
        }
    });
    document.getElementById("createEncryptedBackup")?.addEventListener("click", createEncryptedBackup);
    document.getElementById("restoreEncryptedBackup")?.addEventListener("click", restoreEncryptedBackup);
    workspaceModeButtons.forEach(button => {
        button.addEventListener("click", () => toggleWorkspaceMode(button));
    });
    localExtensionCodeButton?.addEventListener("click", createLocalExtensionPairingCode);
    localExtensionCopyButton?.addEventListener("click", copyLocalExtensionPairingCode);
    deviceTransferCodeButton?.addEventListener("click", createDeviceTransferPairingCode);
    deviceTransferCopyButton?.addEventListener("click", copyDeviceTransferPairingDetails);
    mobileCompanionCodeButton?.addEventListener("click", createMobileCompanionPairingCode);
    revokeMobileCompanionButton?.addEventListener("click", revokeMobileCompanionPairing);
    phoneClipboardToggle?.addEventListener("click", () => {
        if (phoneClipboardAutoCaptureActive) {
            stopPhoneClipboardAutoCapture();
            return;
        }
        enablePhoneClipboardAutoCapture();
    });
    phoneClipboardPasteButton?.addEventListener("click", () => {
        captureCurrentPhoneClipboard();
    });
    phoneClipboardQuickButton?.addEventListener("click", () => {
        captureCurrentPhoneClipboard(true);
    });
    phoneClipboardManualSave?.addEventListener("click", async () => {
        const text = phoneClipboardManualInput?.value || "";
        phoneClipboardManualSave.disabled = true;
        try {
            await savePhoneClipboardText(text);
            if (phoneClipboardManualInput) phoneClipboardManualInput.value = "";
            const message = "Pasted text saved to Stash on the Mac.";
            setStatus(phoneClipboardStatus, message, "success");
            showPhoneClipboardToast(message, "success");
        } catch (error) {
            const message = error.message || "Stash could not save this pasted text.";
            setStatus(phoneClipboardStatus, message, "error");
            showPhoneClipboardToast(message, "error");
        } finally {
            phoneClipboardManualSave.disabled = false;
        }
    });
    document.addEventListener("copy-maker:workspace-ready", async () => {
        await refreshPrivacySettings();
        restorePhoneClipboardAutoCapture();
        refreshCloudStorage({ statusOnly: true });
    });
    closeButton?.addEventListener("click", () => dialog.close());
    checkButton?.addEventListener("click", refreshCloudStorage);
    uploadButton?.addEventListener("click", () => {
        if (storageReady) filePicker?.click();
    });
    filePicker?.addEventListener("change", () => uploadSelectedFiles(Array.from(filePicker.files || [])));
    connectButton?.addEventListener("click", () => {
        const providerButton = document.getElementById("connectAuthButton");
        if (providerButton && !providerButton.hidden) providerButton.click();
        else setStatus(globalStatus, "Google sign-in is not configured yet. Refresh after Firebase setup.", "error");
    });

    document.querySelectorAll("[data-open-integration-folder]").forEach(button => {
        button.addEventListener("click", async () => {
            button.disabled = true;
            setStatus(globalStatus, "Opening the app and its handoff folder…");
            try {
                const response = await fetch("/api/integrations/open-folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ app: button.dataset.openIntegrationFolder }),
                });
                const result = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(result.error || "The folder could not be opened.");
                setStatus(
                    globalStatus,
                    result.appOpened
                        ? `Opened ${result.label} and its import folder.`
                        : `Opened the folder. ${result.label} could not be launched; make sure it is installed.`,
                    "success"
                );
            } catch (error) {
                setStatus(globalStatus, error.message, "error");
            } finally {
                button.disabled = false;
            }
        });
    });
})();
