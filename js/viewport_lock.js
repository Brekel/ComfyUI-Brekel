import { app } from "../../scripts/app.js";

const SETTING_ID = "Brekel.ViewportLock.Locked";

// Test-id of an existing button in the bottom-right canvas cluster (fit-view /
// minimap / links). We anchor to it so our lock button lands in the same group.
const ANCHOR_TESTID = "toggle-link-visibility-button";

let lockButton = null;

const isLocked = () => app.extensionManager.setting.get(SETTING_ID);

const setLocked = (value) => app.extensionManager.setting.set(SETTING_ID, value);

// Single source of truth: push the current state onto the canvas + the button.
function reflectState(value) {
    if (app.canvas) {
        app.canvas.allow_dragcanvas = !value;
        // Uncomment for full "look but don't move" mode (also freezes nodes):
        // app.canvas.allow_dragnodes = !value;
    }
    if (lockButton) {
        const icon = lockButton.querySelector("i.pi");
        if (icon) {
            icon.classList.toggle("pi-lock", value);
            icon.classList.toggle("pi-lock-open", !value);
        }
        // Match the "selected" background the sibling toggle buttons use.
        lockButton.classList.toggle("bg-interface-panel-selected-surface!", value);
        lockButton.title = value
            ? "Viewport locked — pan & zoom disabled (Ctrl+Alt+L)"
            : "Viewport unlocked — click to lock pan & zoom (Ctrl+Alt+L)";
        lockButton.setAttribute("aria-pressed", String(value));
    }
}

// Build the button once, cloning the anchor's classes so it matches the theme.
function mountButton() {
    if (lockButton && lockButton.isConnected) return;

    const anchor = document.querySelector(`[data-testid="${ANCHOR_TESTID}"]`);
    if (!anchor) return; // canvas menu not rendered yet

    const group = anchor.closest(".p-buttongroup") || anchor.parentElement;
    if (!group) return;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = anchor.className; // inherit exact size/shape/hover styling
    btn.setAttribute("data-testid", "brekel-viewport-lock-button");
    btn.innerHTML = `<i class="pi pi-lock-open" style="font-size:14px"></i>`;
    btn.addEventListener("click", (e) => {
        e.stopPropagation();
        setLocked(!isLocked());
    });

    // Append at the end of the cluster (safest against Vue's diffing).
    group.appendChild(btn);
    lockButton = btn;
    reflectState(isLocked());
}

app.registerExtension({
    name: "Brekel.ViewportLock",
    settings: [
        {
            id: SETTING_ID,
            name: "Lock viewport (disable pan & zoom)",
            category: ["Brekel", "Viewport", "Lock viewport"],
            type: "boolean",
            defaultValue: false,
            onChange: (value) => reflectState(value),
        },
    ],
    commands: [
        {
            id: "brekel.viewportlock.toggle",
            label: "Toggle viewport lock",
            function: () => setLocked(!isLocked()),
        },
    ],
    keybindings: [
        { combo: { key: "l", ctrl: true, alt: true }, commandId: "brekel.viewportlock.toggle" },
    ],
    setup() {
        // Swallow wheel zoom / scroll-pan before LiteGraph ever sees it.
        // Capture phase + passive:false so preventDefault works.
        app.canvasEl.addEventListener(
            "wheel",
            (e) => {
                if (isLocked()) {
                    e.stopImmediatePropagation();
                    e.preventDefault();
                }
            },
            { capture: true, passive: false }
        );

        // Try to mount the button now, and re-mount if Vue re-renders the menu
        // (the bottom cluster can be torn down/rebuilt, e.g. toggling the minimap).
        mountButton();
        const observer = new MutationObserver(() => mountButton());
        observer.observe(document.body, { childList: true, subtree: true });

        // Apply the initial state to the canvas.
        reflectState(isLocked());
    },
});
