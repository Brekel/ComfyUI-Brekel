import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "BrekelQueueETA";
const ROUTE = "/brekel/queue_eta";
const STYLE_ID = "brekel-queue-eta-style";

const DEFAULT_SIZE = [280, 220];
const MIN_PANEL_HEIGHT = 118;
// How long the Reset button stays armed, waiting for the confirming second click.
const RESET_CONFIRM_MS = 3000;

// The stats live on the server (brekel_queue_eta.py), so every Queue ETA node on the
// canvas shows the same numbers: node -> the elements of its panel.
const panels = new Map();

let snapshot = null; // last answer from the server
let receivedAt = 0; // performance.now() when it arrived, the countdown runs from there
let ticker = null;
let fetching = false;
let fetchAgain = false;

const STYLE = `
.brekel-eta { display: flex; flex-direction: column; gap: 4px; width: 100%; height: 100%; box-sizing: border-box; overflow: hidden; font-family: system-ui, sans-serif; font-size: 11px; color: var(--input-text, #ddd); user-select: none; }
.brekel-eta-head { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; flex: none; }
.brekel-eta-cell { display: flex; flex-direction: column; align-items: center; padding: 2px; border-radius: 4px; background: var(--comfy-input-bg, #222); }
.brekel-eta-cell > span { max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.brekel-eta-value { font-size: 12px; font-weight: 600; line-height: 1.2; font-variant-numeric: tabular-nums; }
.brekel-eta-caption { font-size: 8px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--descrip-text, #999); }
.brekel-eta-idle { flex: none; padding: 2px 6px; border-radius: 4px; background: var(--comfy-input-bg, #222); }
.brekel-eta-idle-title { font-size: 12px; font-weight: 600; }
.brekel-eta-idle-detail { font-size: 10px; color: var(--descrip-text, #999); }
.brekel-eta-progress { display: flex; align-items: center; gap: 6px; flex: none; font-size: 10px; white-space: nowrap; color: var(--descrip-text, #999); font-variant-numeric: tabular-nums; }
.brekel-eta-bar { flex: 1; height: 4px; border-radius: 2px; overflow: hidden; background: var(--comfy-input-bg, #222); }
.brekel-eta-bar > i { display: block; width: 0; height: 100%; background: var(--p-primary-color, #4ea1ff); transition: width 0.3s; }
.brekel-eta-table { display: grid; grid-template-columns: minmax(0, 1fr) auto auto auto; column-gap: 8px; row-gap: 1px; align-content: start; flex: 1; min-height: 0; overflow-y: auto; font-variant-numeric: tabular-nums; }
.brekel-eta-table > span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.brekel-eta-table > .num { text-align: right; }
.brekel-eta-table > .header { font-size: 8px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--descrip-text, #999); }
.brekel-eta-table > .unqueued { opacity: 0.5; }
.brekel-eta-table > .empty { grid-column: 1 / -1; white-space: normal; color: var(--descrip-text, #999); }
.brekel-eta-foot { display: flex; align-items: center; justify-content: space-between; gap: 6px; flex: none; }
.brekel-eta-last { min-width: 0; font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--descrip-text, #999); }
.brekel-eta-reset { flex: none; padding: 1px 6px; border: 1px solid var(--border-color, #4e4e4e); border-radius: 4px; font: inherit; font-size: 10px; color: inherit; background: var(--comfy-input-bg, #222); cursor: pointer; }
.brekel-eta-reset:hover:not(:disabled) { filter: brightness(1.3); }
.brekel-eta-reset:disabled { opacity: 0.4; cursor: default; }
.brekel-eta-reset.armed { border-color: #d9534f; color: #ff8a80; }
.brekel-eta-shutdown { display: flex; align-items: center; justify-content: space-between; gap: 6px; flex: none; min-height: 16px; font-size: 10px; color: var(--descrip-text, #999); }
.brekel-eta-shutdown > label { display: flex; align-items: center; gap: 4px; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }
.brekel-eta-shutdown input { flex: none; width: 11px; height: 11px; margin: 0; cursor: pointer; }
.brekel-eta-shutdown.on > label { color: #ffb74d; }
.brekel-eta-countdown { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 600; color: #ff8a80; }
`;

function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = STYLE;
    document.head.appendChild(style);
}

function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text != null) el.textContent = text;
    return el;
}

// --- Formatting ---

// Compact duration: 17s, 3m 35s, 1h 05m.
function formatDuration(seconds) {
    const total = Math.round(seconds);
    if (total < 60) return `${total}s`;
    const minutes = Math.floor(total / 60);
    if (minutes < 60) return `${minutes}m ${String(total % 60).padStart(2, "0")}s`;
    return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

// Run times keep a decimal while they are short enough for it to matter.
function formatRun(seconds) {
    return seconds < 60 ? `${seconds.toFixed(1)}s` : formatDuration(seconds);
}

function dayOf(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

// Clock time, with the date in front when it is not today.
function formatClock(date) {
    const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    if (dayOf(date) === dayOf(new Date())) return time;
    return `${date.toLocaleDateString([], { month: "short", day: "numeric" })} ${time}`;
}

// --- Talking to the server ---

function accept(data) {
    snapshot = data;
    receivedAt = performance.now();
    for (const panel of panels.values()) render(panel);
    updateTicker();
}

// The queue announces itself in bursts (queueing 50 prompts is 50 status events), so at most
// one request is in flight and one more is remembered to pick up whatever changed meanwhile.
async function refresh() {
    if (!panels.size) return;
    if (fetching) {
        fetchAgain = true;
        return;
    }
    fetching = true;
    try {
        const response = await api.fetchApi(ROUTE);
        if (response.ok) accept(await response.json());
    } catch (error) {
        console.warn("[Brekel Queue ETA] Could not fetch the queue estimate", error);
    } finally {
        fetching = false;
        if (fetchAgain) {
            fetchAgain = false;
            refresh();
        }
    }
}

async function post(path, body) {
    try {
        const response = await api.fetchApi(`${ROUTE}/${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (response.ok) {
            accept(await response.json());
            return;
        }
        console.warn(`[Brekel Queue ETA] Request '${path}' failed: ${response.status}`);
    } catch (error) {
        console.warn(`[Brekel Queue ETA] Request '${path}' failed`, error);
    }
    // Put the panel back to what the server last said, a checkbox must never show a state the
    // server does not have.
    for (const panel of panels.values()) render(panel);
}

// Forget the stats of one workflow, or of all of them without a signature.
const resetStats = (signature) => post("reset", signature ? { sig: signature } : {});

// Shut the computer down when the queue is done. Switching it off also cancels a shutdown that
// is already counting down. The server keeps this in memory only, so it is off after a restart.
const setShutdown = (armed) => post("shutdown", { armed });

// The server only knows prompts by id, tell it which workflow each queued prompt came
// from so the table can show names instead of hashes.
let queuedNames = {};
let namesTimer = null;

function sendNames() {
    const names = queuedNames;
    queuedNames = {};
    post("names", { names });
}

function reportQueuedNames() {
    const queuePrompt = api.queuePrompt;
    api.queuePrompt = async function (...args) {
        const name = app.extensionManager?.workflow?.activeWorkflow?.filename;
        const result = await queuePrompt.apply(this, args);
        if (name && result?.prompt_id) {
            queuedNames[result.prompt_id] = name;
            // A batch queues its prompts one by one, collect them into a single request.
            clearTimeout(namesTimer);
            namesTimer = setTimeout(sendNames, 100);
        }
        return result;
    };
}

// --- The panel ---

function buildPanel() {
    const root = element("div", "brekel-eta");

    const head = element("div", "brekel-eta-head");
    const cell = (caption) => {
        const box = element("div", "brekel-eta-cell");
        const value = box.appendChild(element("span", "brekel-eta-value", "–"));
        box.appendChild(element("span", "brekel-eta-caption", caption));
        head.appendChild(box);
        return value;
    };
    const left = cell("in queue");
    const time = cell("time left");
    const eta = cell("ETA");

    const idle = element("div", "brekel-eta-idle");
    idle.appendChild(element("div", "brekel-eta-idle-title", "Queue empty"));
    const idleDetail = idle.appendChild(element("div", "brekel-eta-idle-detail"));

    const progress = element("div", "brekel-eta-progress");
    const bar = progress.appendChild(element("div", "brekel-eta-bar")).appendChild(element("i"));
    const progressText = progress.appendChild(element("span"));

    const table = element("div", "brekel-eta-table");

    const shutdown = element("div", "brekel-eta-shutdown");
    const shutdownLabel = shutdown.appendChild(element("label"));
    const shutdownBox = shutdownLabel.appendChild(element("input"));
    shutdownBox.type = "checkbox";
    shutdownLabel.appendChild(element("span", null, "Shut down PC when the queue is done"));
    shutdownLabel.title = "Shuts the computer down 5 minutes after the queue has finished. Switches itself off after use and when ComfyUI restarts.";
    const countdown = shutdown.appendChild(element("span", "brekel-eta-countdown"));
    const cancel = shutdown.appendChild(element("button", "brekel-eta-reset armed", "Cancel shutdown"));
    cancel.type = "button";
    shutdownBox.addEventListener("change", () => setShutdown(shutdownBox.checked));
    cancel.addEventListener("click", (event) => {
        event.stopPropagation();
        setShutdown(false);
    });

    const foot = element("div", "brekel-eta-foot");
    const lastRun = foot.appendChild(element("span", "brekel-eta-last"));
    const reset = foot.appendChild(element("button", "brekel-eta-reset", "Reset stats"));
    reset.type = "button";
    reset.title = "Forget the recorded run times of all workflows";

    root.append(head, idle, progress, table, shutdown, foot);
    const panel = { root, head, left, time, eta, idle, idleDetail, progress, bar, progressText, table, lastRun, reset, shutdown, shutdownLabel, shutdownBox, countdown, cancel };

    // The stats are kept between sessions, so a reset asks for a second click to confirm.
    let armed = null;
    const disarm = () => {
        clearTimeout(armed);
        armed = null;
        reset.classList.remove("armed");
        reset.textContent = "Reset stats";
    };
    reset.addEventListener("click", (event) => {
        event.stopPropagation();
        if (armed) {
            disarm();
            resetStats();
            return;
        }
        reset.classList.add("armed");
        reset.textContent = "Click again to reset";
        armed = setTimeout(disarm, RESET_CONFIRM_MS);
    });

    // The classic renderer lays the panel over the canvas, where it would swallow the mouse
    // wheel. Hand the wheel back to the canvas so zooming keeps working with the pointer over
    // the node (the Nodes 2.0 renderer does this by itself).
    root.addEventListener(
        "wheel",
        (event) => {
            if (window.LiteGraph?.vueNodesMode) return;
            const scrollable = table.scrollHeight > table.clientHeight;
            if (scrollable && table.contains(event.target)) return; // let the table scroll
            event.preventDefault();
            event.stopPropagation();
            app.canvasEl.dispatchEvent(new WheelEvent("wheel", event));
        },
        { passive: false }
    );

    return panel;
}

// The part that changes every second: time left and time of arrival.
function renderCountdown(panel) {
    const unknown = snapshot.unknown;
    if (unknown === snapshot.queue_remaining) {
        // Nothing in the queue has finished a run before, so there is nothing to extrapolate from.
        panel.time.textContent = "–";
        panel.eta.textContent = "–";
        panel.time.parentElement.title = "No finished run of this workflow yet, the estimate appears after the first one";
        return;
    }

    const elapsed = (performance.now() - receivedAt) / 1000;
    const seconds = Math.max(snapshot.running_left - elapsed, 0) + snapshot.pending_seconds;
    // A "+" marks an estimate that leaves out queued prompts of a workflow without run times.
    panel.time.textContent = `~${formatDuration(seconds)}${unknown ? "+" : ""}`;
    panel.eta.textContent = formatClock(new Date(Date.now() + seconds * 1000));
    panel.time.parentElement.title = unknown
        ? `${unknown} queued prompt(s) of a workflow without recorded run times are not included`
        : "";
}

// The countdown of a pending shutdown, also updated every second.
function renderShutdownCountdown(panel) {
    const seconds = snapshot.shutdown?.seconds;
    if (seconds == null) return;
    const exact = seconds - (performance.now() - receivedAt) / 1000;
    // Still here well after the countdown ended: the shutdown was cancelled or refused, ask the
    // server so the panel shows the switch again.
    if (exact < -3) refresh();
    const left = Math.max(Math.round(exact), 0);
    panel.countdown.textContent = `Shutting down in ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
}

function renderShutdown(panel) {
    const state = snapshot.shutdown ?? { armed: false, seconds: null, error: null };
    const pending = state.seconds != null;
    panel.shutdown.classList.toggle("on", state.armed);
    panel.shutdownLabel.style.display = pending ? "none" : "";
    panel.countdown.style.display = pending ? "" : "none";
    panel.cancel.style.display = pending ? "" : "none";
    panel.shutdownBox.checked = state.armed;
    panel.shutdownLabel.lastChild.textContent = state.error
        ? "Shutdown command failed, see the console"
        : "Shut down PC when the queue is done";
    renderShutdownCountdown(panel);
}

function renderTable(panel) {
    const cells = [
        element("span", "header", "Workflow"),
        element("span", "header num", "Queued"),
        element("span", "header num", "Median"),
        element("span", "header num", "Runs"),
    ];
    for (const workflow of snapshot.workflows) {
        const dim = workflow.queued ? "" : " unqueued";
        const label = element("span", dim, workflow.label);
        label.title = workflow.label;
        cells.push(
            label,
            element("span", `num${dim}`, String(workflow.queued)),
            element("span", `num${dim}`, workflow.median == null ? "–" : formatRun(workflow.median)),
            element("span", `num${dim}`, String(workflow.runs))
        );
    }
    if (!snapshot.workflows.length) {
        cells.push(element("span", "empty", "No runs recorded yet, queue a workflow and its run times show up here."));
    }
    panel.table.replaceChildren(...cells);
}

function render(panel) {
    if (!snapshot) return;
    const busy = snapshot.queue_remaining > 0;
    panel.head.style.display = busy ? "" : "none";
    panel.progress.style.display = busy ? "" : "none";
    panel.idle.style.display = busy ? "none" : "";

    if (busy) {
        // Progress counts from the moment the queue was last empty.
        const total = snapshot.batch_done + snapshot.queue_remaining;
        panel.left.textContent = String(snapshot.queue_remaining);
        panel.bar.style.width = `${(100 * snapshot.batch_done) / total}%`;
        panel.progressText.textContent = `${snapshot.batch_done} of ${total} done`;
        renderCountdown(panel);
    } else {
        const batch = snapshot.last_batch;
        panel.idleDetail.textContent = batch
            ? `Last batch: ${batch.runs} ${batch.runs === 1 ? "run" : "runs"} in ${formatDuration(batch.seconds)}, done at ${formatClock(new Date(Date.now() - batch.finished_ago * 1000))}`
            : "No batch finished yet";
    }

    renderTable(panel);
    renderShutdown(panel);

    const last = snapshot.last_run;
    panel.lastRun.textContent = last ? `Last run: ${formatRun(last.seconds)} (${last.label})` : "";
    panel.lastRun.title = panel.lastRun.textContent;
    panel.reset.disabled = !snapshot.workflows.some((workflow) => workflow.runs > 0);
}

// The countdowns only need to tick while something is queued or a shutdown is pending, and a
// node is there to show it.
function updateTicker() {
    const busy = snapshot?.queue_remaining > 0;
    const wanted = panels.size > 0 && (busy || snapshot?.shutdown?.seconds != null);
    if (wanted && !ticker) {
        ticker = setInterval(() => {
            for (const panel of panels.values()) {
                if (snapshot.queue_remaining > 0) renderCountdown(panel);
                renderShutdownCountdown(panel);
            }
        }, 1000);
    } else if (!wanted && ticker) {
        clearInterval(ticker);
        ticker = null;
    }
}

function setupNode(node) {
    injectStyle();
    const panel = buildPanel();

    const widget = node.addDOMWidget("queue_eta", "brekel_queue_eta", panel.root, {
        // Display only: nothing to save in the workflow and nothing to send with the prompt.
        serialize: false,
        hideOnZoom: false,
        hideInPanel: true,
        getValue: () => "",
        setValue: () => {},
        getMinHeight: () => MIN_PANEL_HEIGHT,
    });
    widget.serialize = false;

    // Only a freshly added node keeps this size, a loaded workflow restores its own right after.
    node.setSize([...DEFAULT_SIZE]);

    panels.set(node, panel);
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
        panels.delete(node);
        updateTicker();
        return onRemoved?.apply(this, arguments);
    };

    render(panel);
    refresh();
}

const isQueueEtaNode = (node) => node?.constructor?.comfyClass === NODE_NAME || node?.type === NODE_NAME;

app.registerExtension({
    name: "Brekel.QueueETA",
    setup() {
        // The server announces every queue change (queued, started, finished, deleted).
        api.addEventListener("status", refresh);
        api.addEventListener("reconnected", refresh);
        reportQueuedNames();
    },
    nodeCreated(node) {
        if (isQueueEtaNode(node)) setupNode(node);
    },
    getNodeMenuItems(node) {
        if (!isQueueEtaNode(node)) return [];
        const known = (snapshot?.workflows ?? []).filter((workflow) => workflow.runs > 0);
        return [
            null,
            {
                content: "Reset Queue ETA stats for",
                disabled: !known.length,
                has_submenu: true,
                submenu: {
                    options: known.map((workflow) => ({
                        content: workflow.label,
                        callback: () => resetStats(workflow.sig),
                    })),
                },
            },
            {
                content: "Reset all Queue ETA stats",
                disabled: !known.length,
                callback: () => resetStats(),
            },
        ];
    },
});
