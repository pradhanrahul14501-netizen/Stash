"use strict";

(() => {
    const navigation = document.getElementById("vaultNavigation");
    const dialog = document.getElementById("vaultDialog");
    if (!navigation || !dialog) return;

    const closeButton = document.getElementById("closeVaultDialog");
    const status = document.getElementById("vaultStatus");
    const setupPanel = document.getElementById("vaultSetupPanel");
    const unlockPanel = document.getElementById("vaultUnlockPanel");
    const unlockedPanel = document.getElementById("vaultUnlockedPanel");
    const newPassword = document.getElementById("vaultNewPassword");
    const confirmPassword = document.getElementById("vaultConfirmPassword");
    const password = document.getElementById("vaultPassword");
    const createButton = document.getElementById("createVaultButton");
    const unlockButton = document.getElementById("unlockVaultButton");
    const lockButton = document.getElementById("lockVaultButton");
    const captureAllButton = document.getElementById("toggleVaultCaptureAll");
    const idleLockMinutes = document.getElementById("vaultIdleLockMinutes");
    const idleLockStatus = document.getElementById("vaultIdleLockStatus");
    const titleInput = document.getElementById("vaultEntryTitle");
    const contentInput = document.getElementById("vaultEntryContent");
    const saveEntryButton = document.getElementById("saveVaultEntryButton");
    const entryList = document.getElementById("vaultEntryList");
    const entriesSummary = document.getElementById("vaultEntriesSummary");
    const navCount = document.getElementById("vaultCount");

    let currentStatus = null;
    let loadedEntries = false;
    let isRefreshing = false;

    function reactAsAva(detail) {
        window.dispatchEvent(new CustomEvent("stash:ava-reaction", { detail }));
    }

    function setMessage(message, kind = "") {
        status.textContent = message;
        if (kind) status.dataset.kind = kind;
        else delete status.dataset.kind;
    }

    async function api(path, options = {}) {
        const response = await fetch(path, {
            cache: "no-store",
            ...options,
            headers: {
                ...(options.body ? { "Content-Type": "application/json" } : {}),
                ...(options.headers || {}),
            },
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.error || "Stash could not complete that Vault action.");
        return result;
    }

    function clearRevealedSecrets() {
        entryList.querySelectorAll(".vault-secret").forEach(element => {
            element.textContent = "";
            element.hidden = true;
        });
        entryList.querySelectorAll("[data-vault-reveal]").forEach(button => {
            button.textContent = "Reveal";
        });
    }

    function clearPasswordInputs() {
        [newPassword, confirmPassword, password].forEach(input => {
            if (input) input.value = "";
        });
    }

    function renderStatus(value) {
        const wasUnlocked = currentStatus?.unlocked === true;
        currentStatus = value;
        navCount.textContent = String(value.entry_count);

        setupPanel.hidden = value.configured;
        unlockPanel.hidden = !value.configured || value.unlocked;
        unlockedPanel.hidden = !value.unlocked;
        captureAllButton.setAttribute("aria-pressed", String(value.capture_all_text));
        captureAllButton.textContent = value.capture_all_text
            ? "Capture all text: On"
            : "Capture all text: Off";
        captureAllButton.classList.toggle("is-enabled", value.capture_all_text);
        if (idleLockMinutes) idleLockMinutes.value = String(value.idle_lock_minutes || 5);
        if (idleLockStatus) idleLockStatus.textContent = `Vault locks after ${value.idle_lock_minutes || 5} ${Number(value.idle_lock_minutes || 5) === 1 ? "minute" : "minutes"} without Vault activity.`;

        if (!value.configured) {
            setMessage("Create a Vault password. Sensitive copies are discarded until the Vault is ready and unlocked.", "warning");
        } else if (!value.unlocked) {
            setMessage(`Vault locked · ${value.entry_count} encrypted ${value.entry_count === 1 ? "item" : "items"}. Sensitive copies are discarded until you unlock it.`, "warning");
        } else {
            setMessage(`Vault unlocked · ${value.entry_count} encrypted ${value.entry_count === 1 ? "item" : "items"}.`, "success");
        }

        if (wasUnlocked && !value.unlocked) {
            clearRevealedSecrets();
            entryList.replaceChildren();
            loadedEntries = false;
            if (titleInput) titleInput.value = "";
            if (contentInput) contentInput.value = "";
            clearPasswordInputs();
        }
        if (!wasUnlocked && value.unlocked && !dialog.open) loadedEntries = false;
    }

    async function refreshStatus({ loadEntries = false } = {}) {
        if (isRefreshing) {
            await new Promise(resolve => window.setTimeout(resolve, 120));
            return refreshStatus({ loadEntries });
        }
        isRefreshing = true;
        try {
            const value = await api("/api/vault/status");
            const wasUnlocked = currentStatus?.unlocked === true;
            const previousCount = currentStatus?.entry_count;
            renderStatus(value);
            if (value.unlocked && dialog.open && (
                loadEntries || !loadedEntries || !wasUnlocked || value.entry_count !== previousCount
            )) {
                await refreshEntries();
            }
        } catch (error) {
            setMessage(error.message || "Stash could not read the Vault status.", "error");
        } finally {
            isRefreshing = false;
        }
    }

    function formatDate(value) {
        const date = new Date(value);
        return Number.isNaN(date.getTime())
            ? ""
            : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
    }

    async function fetchEntryContent(id) {
        const result = await api(`/api/vault/entries/${encodeURIComponent(id)}`);
        return result.entry;
    }

    async function refreshEntries() {
        const result = await api("/api/vault/entries");
        loadedEntries = true;
        entryList.replaceChildren();
        const entries = Array.isArray(result.entries) ? result.entries : [];
        entriesSummary.textContent = `${entries.length} encrypted ${entries.length === 1 ? "item" : "items"}. Secret text stays hidden until you reveal or copy it.`;

        if (!entries.length) {
            const empty = document.createElement("p");
            empty.className = "settings-status vault-empty-state";
            empty.textContent = "Your Vault is empty. Sensitive copies will appear here automatically.";
            entryList.append(empty);
            return;
        }

        entries.forEach(entry => {
            const row = document.createElement("article");
            row.className = "vault-entry-row";
            const heading = document.createElement("div");
            heading.className = "vault-entry-heading";
            const name = document.createElement("strong");
            name.textContent = entry.title || "Secure copy";
            const date = document.createElement("span");
            date.textContent = formatDate(entry.created_at);
            heading.append(name, date);

            const actions = document.createElement("div");
            actions.className = "vault-entry-actions";
            const reveal = document.createElement("button");
            reveal.className = "settings-secondary-button";
            reveal.type = "button";
            reveal.textContent = "Reveal";
            const copy = document.createElement("button");
            copy.className = "settings-secondary-button";
            copy.type = "button";
            copy.textContent = "Copy";
            const remove = document.createElement("button");
            remove.className = "settings-danger-button";
            remove.type = "button";
            remove.textContent = "Delete";

            const secret = document.createElement("pre");
            secret.className = "vault-secret phone-clipboard-manual-input";
            secret.hidden = true;

            reveal.addEventListener("click", async () => {
                if (!secret.hidden) {
                    secret.textContent = "";
                    secret.hidden = true;
                    reveal.textContent = "Reveal";
                    return;
                }
                reveal.disabled = true;
                try {
                    const value = await fetchEntryContent(entry.id);
                    secret.textContent = value.content;
                    secret.hidden = false;
                    reveal.textContent = "Hide";
                    window.setTimeout(() => {
                        if (!secret.isConnected) return;
                        secret.textContent = "";
                        secret.hidden = true;
                        reveal.textContent = "Reveal";
                    }, 30_000);
                } catch (error) {
                    setMessage(error.message, "error");
                } finally {
                    reveal.disabled = false;
                }
            });

            copy.addEventListener("click", async () => {
                copy.disabled = true;
                try {
                    const value = await fetchEntryContent(entry.id);
                    await navigator.clipboard.writeText(value.content);
                    setMessage("Copied from the Vault. Stash will keep it out of the regular library.", "success");
                } catch (error) {
                    setMessage(error.message || "Your browser did not allow copying this Vault item.", "error");
                } finally {
                    copy.disabled = false;
                }
            });

            remove.addEventListener("click", async () => {
                if (!window.confirm("Permanently delete this encrypted Vault item?")) return;
                remove.disabled = true;
                try {
                    await api(`/api/vault/entries/${encodeURIComponent(entry.id)}`, { method: "DELETE" });
                    await refreshStatus({ loadEntries: true });
                } catch (error) {
                    setMessage(error.message, "error");
                    remove.disabled = false;
                }
            });

            actions.append(reveal, copy, remove);
            row.append(heading, actions, secret);
            entryList.append(row);
        });
    }

    async function postPassword(path, value) {
        const result = await api(path, {
            method: "POST",
            body: JSON.stringify(value),
        });
        clearPasswordInputs();
        loadedEntries = false;
        await refreshStatus({ loadEntries: true });
        reactAsAva({
            mood: "happy",
            message: path.endsWith("/unlock")
                ? "Phew! Vault unlocked. Your secret stuff is back behind the lock."
                : "Vault created! I’ll help keep those secrets under lock and key.",
            action: "hopping",
            duration: 5000,
            modal: true,
            speak: true,
        });
    }

    async function closeVault() {
        try {
            await api("/api/vault/lock", { method: "POST", body: "{}" });
            clearRevealedSecrets();
            entryList.replaceChildren();
            loadedEntries = false;
            clearPasswordInputs();
            if (titleInput) titleInput.value = "";
            if (contentInput) contentInput.value = "";
            dialog.close();
            window.dispatchEvent(new CustomEvent("stash:ava-return-home"));
            navigation.classList.remove("active");
            await refreshStatus();
        } catch (error) {
            setMessage(error.message || "Stash could not lock the Vault.", "error");
            await refreshStatus();
        }
    }

    navigation.addEventListener("click", async () => {
        document.querySelectorAll(".nav-item").forEach(button => button.classList.remove("active"));
        navigation.classList.add("active");
        dialog.showModal();
        await refreshStatus({ loadEntries: true });
        if (currentStatus?.configured && !currentStatus.unlocked) password.focus();
        else if (!currentStatus?.configured) newPassword.focus();
    });

    closeButton.addEventListener("click", closeVault);
    dialog.addEventListener("cancel", event => {
        event.preventDefault();
        closeVault();
    });
    dialog.addEventListener("click", event => {
        if (event.target === dialog) closeVault();
    });

    createButton.addEventListener("click", async () => {
        createButton.disabled = true;
        try {
            await postPassword("/api/vault/setup", {
                password: newPassword.value,
                confirmation: confirmPassword.value,
            });
        } catch (error) {
            setMessage(error.message, "error");
        } finally {
            createButton.disabled = false;
        }
    });

    unlockButton.addEventListener("click", async () => {
        unlockButton.disabled = true;
        try {
            await postPassword("/api/vault/unlock", { password: password.value });
        } catch (error) {
            if (error.message === "That Vault password is not correct.") {
                setMessage("😟 Ava says: Oops, that password didn’t fit. Try the exact one you chose; Vault passwords can’t be reset.", "error");
                reactAsAva({
                    mood: "worried",
                    message: "Oops, that password didn’t fit. Try the exact one you chose; Vault passwords can’t be reset.",
                    action: "peeking",
                    duration: 6200,
                    modal: true,
                    speak: true,
                });
            } else {
                setMessage(error.message, "error");
            }
            password.focus();
        } finally {
            unlockButton.disabled = false;
        }
    });
    password.addEventListener("keydown", event => {
        if (event.key === "Enter") unlockButton.click();
    });

    lockButton.addEventListener("click", closeVault);

    captureAllButton.addEventListener("click", async () => {
        captureAllButton.disabled = true;
        try {
            const result = await api("/api/vault/capture-all", {
                method: "POST",
                body: JSON.stringify({ enabled: !currentStatus?.capture_all_text }),
            });
            await refreshStatus();
            setMessage(result.enabled
                ? "All copied text will be saved to the Vault until you turn this off."
                : "Only text Stash recognizes as sensitive will be sent to the Vault.", "success");
        } catch (error) {
            setMessage(error.message, "error");
        } finally {
            captureAllButton.disabled = false;
        }
    });

    idleLockMinutes?.addEventListener("change", async () => {
        idleLockMinutes.disabled = true;
        try {
            const result = await api("/api/vault/settings", {
                method: "POST",
                body: JSON.stringify({ idle_lock_minutes: Number(idleLockMinutes.value) }),
            });
            idleLockMinutes.value = String(result.idle_lock_minutes);
            idleLockStatus.textContent = `Vault locks after ${result.idle_lock_minutes} ${result.idle_lock_minutes === 1 ? "minute" : "minutes"} without Vault activity.`;
            setMessage("Vault auto-lock setting saved.", "success");
        } catch (error) {
            setMessage(error.message, "error");
            await refreshStatus();
        } finally {
            idleLockMinutes.disabled = false;
        }
    });

    saveEntryButton.addEventListener("click", async () => {
        saveEntryButton.disabled = true;
        try {
            await api("/api/vault/entries", {
                method: "POST",
                body: JSON.stringify({ title: titleInput.value, content: contentInput.value }),
            });
            titleInput.value = "";
            contentInput.value = "";
            await refreshStatus({ loadEntries: true });
            setMessage("Saved as an encrypted Vault item.", "success");
        } catch (error) {
            setMessage(error.message, "error");
        } finally {
            saveEntryButton.disabled = false;
        }
    });

    document.addEventListener("copy-maker:workspace-ready", () => refreshStatus());
    window.setInterval(() => refreshStatus(), 5000);
})();
