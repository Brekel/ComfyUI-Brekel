#
# Brekel Queue ETA Node for ComfyUI
# Version: 1.0.0
#
# Author: Brekel - https://brekel.com
#
# This node estimates how long the rest of the queue will take. Every finished prompt is timed,
# the times are kept per type of workflow, and those are used to predict the time left and the
# time of arrival for everything that is still queued.
# The measuring happens here on the server, so it keeps working when the browser tab is closed
# or reloaded. The node itself is only a display, its panel lives in js/queue_eta.js.


# --- CONFIGURATION CONSTANTS ---
# How many of the most recent run times are kept per workflow, the estimate is their median.
RUNS_PER_WORKFLOW = 10
# How many different workflows are remembered, the least recently used one is dropped first.
MAX_WORKFLOWS = 100
# Name of the file in the ComfyUI user directory that the stats are saved to.
STATS_FILENAME = "brekel_queue_eta.json"
# How many prompt ids are remembered for the signature / workflow name lookups.
MAX_PROMPT_IDS = 5000
# Seconds between the queue finishing and the computer shutting down (when that was asked for),
# the window in which the shutdown can still be cancelled.
SHUTDOWN_DELAY = 300


import os
import json
import time
import asyncio
import hashlib
import logging
import statistics
import subprocess
import threading

# import block to communicate with the frontend
try:
    from server import PromptServer
except ImportError:
    # If the server is not available (e.g., in a headless environment) create a dummy class to prevent errors.
    class PromptServer:
        instance = None


# --- Setup basic logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LOG_PREFIX = "[Brekel Queue ETA]"


def _is_link(value):
    """True when an input value is a connection to another node: [node_id, output_index]."""
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], (int, float))
    )


def workflow_signature(prompt, outputs=None):
    """
    Identify the type of workflow: a hash of the nodes that actually run (everything upstream
    of the outputs), their class types and their connections. Widget values are left out on
    purpose, so runs that only differ in seed or prompt text share their timings.
    """
    if not isinstance(prompt, dict):
        return "unknown"

    wanted = [str(node_id) for node_id in outputs] if outputs else list(prompt)
    reached = set()
    while wanted:
        node_id = wanted.pop()
        node = prompt.get(node_id)
        if node_id in reached or not isinstance(node, dict):
            continue
        reached.add(node_id)
        for value in (node.get("inputs") or {}).values():
            if _is_link(value):
                wanted.append(value[0])

    parts = []
    for node_id in sorted(reached):
        node = prompt[node_id]
        links = sorted(
            (name, value[0], int(value[1]))
            for name, value in (node.get("inputs") or {}).items()
            if _is_link(value)
        )
        parts.append([node_id, str(node.get("class_type", "")), links])

    return hashlib.sha1(json.dumps(parts).encode("utf-8")).hexdigest()[:12]


def format_duration(seconds):
    """Compact duration: 17s, 3m 35s, 1h 05m."""
    total = int(round(seconds))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _format_run(seconds):
    """Run times keep their decimals while they are short enough for those to matter."""
    return f"{seconds:.2f}s" if seconds < 60 else format_duration(seconds)


def _trim(mapping, limit):
    """Drop the oldest entries of a dict until it holds at most `limit` items."""
    while len(mapping) > limit:
        mapping.pop(next(iter(mapping)))


# --- QUEUE ETA TRACKER CLASS ---
class QueueEtaTracker:
    """
    Keeps the run times per workflow and turns the current queue into an estimate.
    Queue items are ComfyUI's own tuples: (number, prompt_id, prompt, extra_data, outputs_to_execute, ...).
    """

    def __init__(self, stats_path=None, clock=time.time, timer=time.monotonic):
        self.stats_path = stats_path
        # Durations are measured with `timer`, which a change of the system clock cannot disturb.
        # `clock` is only used for the moments that are shown or saved (last run, batch finished).
        self.clock = clock
        self.timer = timer
        # The prompt worker thread records the runs, the web server thread asks for snapshots.
        self.lock = threading.Lock()

        self.workflows = {}        # signature -> {"label", "durations", "runs", "last_run"}, ordered by last use
        self.last_run = None       # {"label", "seconds"}
        self.last_batch = None     # {"runs", "seconds", "finished"}
        self.batch_started = None  # timer value when the queue started running, None while it is empty
        self.batch_done = 0        # prompts finished since the queue was last empty

        self.started = {}          # prompt_id -> timer value when it started running
        self.signatures = {}       # prompt_id -> signature, so a long queue is not hashed again on every request
        self.names = {}            # prompt_id -> workflow name reported by the frontend

        self._load()

    # --- Persistence ---
    def _load(self):
        if not self.stats_path or not os.path.isfile(self.stats_path):
            return
        try:
            with open(self.stats_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for signature, entry in data.get("workflows", {}).items():
                durations = [float(d) for d in entry["durations"]][-RUNS_PER_WORKFLOW:]
                if not durations:
                    continue
                self.workflows[str(signature)] = {
                    "label": str(entry.get("label") or signature[:6]),
                    "durations": durations,
                    "runs": int(entry.get("runs", len(durations))),
                    "last_run": float(entry.get("last_run", 0)),
                }
            last_run = data.get("last_run")
            if last_run:
                self.last_run = {"label": str(last_run["label"]), "seconds": float(last_run["seconds"])}
            last_batch = data.get("last_batch")
            if last_batch:
                self.last_batch = {
                    "runs": int(last_batch["runs"]),
                    "seconds": float(last_batch["seconds"]),
                    "finished": float(last_batch["finished"]),
                }
        except Exception as e:
            logger.error(f"{LOG_PREFIX} Could not read the saved stats from '{self.stats_path}', starting empty: {e}")
            self.workflows = {}
            self.last_run = None
            self.last_batch = None

    def _save(self):
        if not self.stats_path:
            return
        data = {
            "version": 1,
            "workflows": self.workflows,
            "last_run": self.last_run,
            "last_batch": self.last_batch,
        }
        try:
            # Write to a temp file first so a crash mid-write can never leave a half written stats file.
            temp_path = self.stats_path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
            os.replace(temp_path, self.stats_path)
        except Exception as e:
            logger.error(f"{LOG_PREFIX} Could not save the stats to '{self.stats_path}': {e}")

    # --- Lookups (call with the lock held) ---
    def _signature_of(self, item):
        prompt_id = item[1]
        signature = self.signatures.get(prompt_id)
        if signature is None:
            outputs = item[4] if len(item) > 4 else None
            signature = workflow_signature(item[2], outputs)
            self.signatures[prompt_id] = signature
            _trim(self.signatures, MAX_PROMPT_IDS)
        return signature

    def _label_of(self, item, signature):
        """The workflow name when the frontend reported one, otherwise the last known label or a short hash."""
        entry = self.workflows.get(signature)
        name = self.names.get(item[1])
        if name:
            if entry:
                entry["label"] = name
            return name
        return entry["label"] if entry else signature[:6]

    def _median_of(self, signature):
        entry = self.workflows.get(signature)
        return statistics.median(entry["durations"]) if entry else None

    # --- Events from the queue ---
    def on_start(self, item):
        """A prompt was taken from the queue and starts running."""
        with self.lock:
            now = self.timer()
            self.started[item[1]] = now
            _trim(self.started, MAX_PROMPT_IDS)
            if self.batch_started is None:
                self.batch_started = now
                self.batch_done = 0

    def on_done(self, item, success, remaining):
        """
        A prompt finished, `remaining` is the number of prompts left in the queue after it.
        Only successful runs are recorded, an interrupted or failed run gives a misleading time.
        """
        with self.lock:
            now = self.clock()
            ended = self.timer()
            seconds = ended - self.started.pop(item[1], ended)
            signature = self._signature_of(item)
            label = self._label_of(item, signature)
            self.batch_done += 1

            if success:
                entry = self.workflows.pop(signature, None) or {"durations": [], "runs": 0}
                entry["label"] = label
                entry["durations"] = (entry["durations"] + [seconds])[-RUNS_PER_WORKFLOW:]
                entry["runs"] += 1
                entry["last_run"] = now
                # Re-inserted at the end, which keeps the dict ordered by last use for _trim.
                self.workflows[signature] = entry
                _trim(self.workflows, MAX_WORKFLOWS)
                self.last_run = {"label": label, "seconds": seconds}

            batch = None
            if remaining <= 0:
                started = self.batch_started if self.batch_started is not None else ended
                batch = {"runs": self.batch_done, "seconds": ended - started, "finished": now}
                self.last_batch = batch
                self.batch_started = None

            if success or batch:
                self._save()

            entry = self.workflows.get(signature)
            return {
                "label": label,
                "seconds": seconds,
                "success": success,
                "median": self._median_of(signature),
                "runs": entry["runs"] if entry else 0,
                "batch": batch,
            }

    # --- Requests from the frontend ---
    def set_names(self, names):
        """Remember which workflow each prompt id was queued from: {prompt_id: workflow name}."""
        if not isinstance(names, dict):
            return
        with self.lock:
            for prompt_id, name in names.items():
                if not isinstance(name, str) or not name.strip():
                    continue
                name = name.strip()[:80]
                self.names[str(prompt_id)] = name
                # A short run can be finished before its name arrives, label it after the fact.
                entry = self.workflows.get(self.signatures.get(str(prompt_id)))
                if entry:
                    entry["label"] = name
            _trim(self.names, MAX_PROMPT_IDS)

    def reset(self, signature=None):
        """
        Forget the stats of one workflow, or of everything when no signature is given.
        Returns the number of workflows that were forgotten.
        """
        with self.lock:
            before = len(self.workflows)
            if signature is None:
                self.workflows = {}
                self.last_run = None
                self.last_batch = None
            else:
                self.workflows.pop(signature, None)
            self._save()
            return before - len(self.workflows)

    def snapshot(self, running, pending):
        """Estimate the given queue (lists of queue items) and report the stats per workflow."""
        with self.lock:
            now = self.clock()
            timer_now = self.timer()
            queued = {}   # signature -> number of prompts in the queue
            labels = {}
            running_left = 0.0
            pending_seconds = 0.0
            unknown = 0

            for is_running, items in ((True, running), (False, pending)):
                for item in items:
                    signature = self._signature_of(item)
                    queued[signature] = queued.get(signature, 0) + 1
                    # A name reported for any prompt of this workflow wins over the fallback label.
                    if signature not in labels or item[1] in self.names:
                        labels[signature] = self._label_of(item, signature)
                    median = self._median_of(signature)
                    if median is None:
                        unknown += 1
                    elif is_running:
                        elapsed = timer_now - self.started.setdefault(item[1], timer_now)
                        running_left += max(median - elapsed, 0.0)
                    else:
                        pending_seconds += median

            rows = []
            for signature in set(self.workflows) | set(queued):
                entry = self.workflows.get(signature)
                rows.append({
                    "sig": signature,
                    "label": labels.get(signature) or entry["label"],
                    "queued": queued.get(signature, 0),
                    "median": self._median_of(signature),
                    "runs": entry["runs"] if entry else 0,
                    "last_run": entry["last_run"] if entry else now,
                })
            # What is queued comes first, then whatever ran most recently.
            rows.sort(key=lambda row: (row["queued"] == 0, -row["queued"], -row["last_run"]))
            for row in rows:
                del row["last_run"]

            last_batch = None
            if self.last_batch:
                last_batch = {
                    "runs": self.last_batch["runs"],
                    "seconds": self.last_batch["seconds"],
                    # Sent as an age instead of a timestamp, so the browser's clock does not have to match the server's.
                    "finished_ago": max(now - self.last_batch["finished"], 0.0),
                }

            return {
                "queue_remaining": len(running) + len(pending),
                "running_left": running_left,
                "pending_seconds": pending_seconds,
                "unknown": unknown,
                "batch_done": self.batch_done if self.batch_started is not None else 0,
                "last_run": self.last_run,
                "last_batch": last_batch,
                "workflows": rows,
            }


# --- Shutting down the computer when the queue is done ---
def run_system_command(args):
    """Run a shutdown command of the operating system, raises when it fails."""
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or f"exit code {result.returncode}").strip())


class ShutdownSwitch:
    """
    The 'shut down when the queue is done' switch. It only lives in memory on purpose: it is
    off after every restart of ComfyUI and switches itself off again once it has been used,
    so a shutdown always has to be asked for explicitly.
    The shutdown commands run outside the lock, so the web server can always answer quickly.
    """

    def __init__(self, clock=time.monotonic, run=None, notify=None):
        self.clock = clock
        self.run = run
        self.notify = notify   # tells the open browser tabs that the state changed
        self.lock = threading.Lock()
        self.armed = False     # shut down once the queue is done
        self.deadline = None   # clock value at which the computer goes down, set while a shutdown is pending
        self.error = None      # why the last shutdown command failed
        self.changes = 0       # counts the user's switches, so a slow command cannot undo a newer choice

    def _command(self, args):
        """Run a shutdown command, returns the error message when it failed."""
        try:
            (self.run or run_system_command)(args)
            return None
        except Exception as e:
            return str(e) or type(e).__name__

    def _abort(self):
        """Call off the pending shutdown, False when that failed (for example because it was already cancelled)."""
        error = self._command(["shutdown", "/a"] if os.name == "nt" else ["shutdown", "-c"])
        if error:
            logger.warning(f"{LOG_PREFIX} Could not cancel the shutdown, it may have been cancelled already: {error}")
            return False
        print(f"{LOG_PREFIX} Shutdown cancelled", flush=True)
        return True

    def _pending(self):
        """True while a shutdown is counting down (call with the lock held)."""
        if self.deadline is not None and self.clock() >= self.deadline:
            # The moment has passed and ComfyUI still runs, so the shutdown was cancelled outside
            # the node or refused by the system: show the plain switch again.
            self.deadline = None
        return self.deadline is not None

    def _notify(self):
        if self.notify:
            try:
                self.notify()
            except Exception:
                logger.exception(f"{LOG_PREFIX} Could not announce the shutdown state")

    def set_armed(self, armed):
        """Switch on or off, switching off also cancels a shutdown that is already counting down."""
        with self.lock:
            self.changes += 1
            self.error = None
            pending = self._pending()
            self.deadline = None
            self.armed = bool(armed)
        if pending:
            self._abort()
        self._notify()

    def queue_started(self):
        """
        New work arrived while the shutdown was counting down: call it off and wait for the
        queue to finish again. Only when the shutdown could really be called off, when that
        fails it was most likely cancelled already (with 'shutdown /a') and must not come back.
        """
        with self.lock:
            if not self._pending():
                return
            self.deadline = None
            changes = self.changes
        cancelled = self._abort()
        with self.lock:
            if cancelled and changes == self.changes:
                self.armed = True
        self._notify()

    def queue_finished(self):
        """The queue is empty: when switched on, start the countdown to the shutdown."""
        with self.lock:
            if not self.armed:
                return
            self.armed = False
            changes = self.changes
        minutes = max(round(SHUTDOWN_DELAY / 60), 1)
        if os.name == "nt":
            args = ["shutdown", "/s", "/t", str(SHUTDOWN_DELAY), "/c", "The ComfyUI queue has finished (Brekel Queue ETA)."]
        else:
            args = ["shutdown", "-h", f"+{minutes}"]
        error = self._command(args)
        with self.lock:
            # The user switched it off again while the command ran.
            withdrawn = changes != self.changes
            if error:
                self.error = error
            elif not withdrawn:
                self.deadline = self.clock() + SHUTDOWN_DELAY
        if error:
            logger.error(f"{LOG_PREFIX} Could not start the shutdown: {error}")
        elif withdrawn:
            self._abort()
        else:
            print(f"{LOG_PREFIX} Queue finished, the computer shuts down in {format_duration(SHUTDOWN_DELAY)}. "
                  f"Cancel it on the Queue ETA node or with '{'shutdown /a' if os.name == 'nt' else 'shutdown -c'}'", flush=True)

    def state(self):
        with self.lock:
            seconds = max(self.deadline - self.clock(), 0.0) if self._pending() else None
            return {"armed": self.armed, "seconds": seconds, "error": self.error}


# --- Hooking into the ComfyUI queue ---
def current_queue(prompt_queue):
    """The running and the pending queue items."""
    if hasattr(prompt_queue, "get_current_queue_volatile"):
        return prompt_queue.get_current_queue_volatile()
    return prompt_queue.get_current_queue()


def _console_line(done, estimate, now):
    """One line of stats for the console, printed next to ComfyUI's own 'Prompt executed in'."""
    if done["success"]:
        line = f"{done['label']}: {_format_run(done['seconds'])} (median {_format_run(done['median'])} over {done['runs']} runs)"
    else:
        line = f"{done['label']}: failed or interrupted after {_format_run(done['seconds'])}, not counted"

    remaining = estimate["queue_remaining"]
    if done["batch"]:
        line += f" | queue finished, {done['batch']['runs']} runs in {format_duration(done['batch']['seconds'])}"
    elif estimate["unknown"] == remaining:
        line += f" | {remaining} left, no estimate yet"
    else:
        seconds_left = estimate["running_left"] + estimate["pending_seconds"]
        more = "+" if estimate["unknown"] else ""
        eta = time.strftime("%H:%M:%S", time.localtime(now + seconds_left))
        line += f" | {remaining} left, ~{format_duration(seconds_left)}{more}, ETA {eta}"
    return line


def install_hooks(prompt_queue, tracker, shutdown=None):
    """
    Wrap the queue's get / task_done so every prompt is timed from the moment it leaves the
    queue until it is marked done, the same span ComfyUI reports as 'Prompt executed in'.
    Returns False when the queue is already hooked.
    """
    if getattr(prompt_queue, "_brekel_queue_eta_hooked", False):
        return False
    prompt_queue._brekel_queue_eta_hooked = True

    original_get = prompt_queue.get
    original_task_done = prompt_queue.task_done

    def get(*args, **kwargs):
        result = original_get(*args, **kwargs)
        if result is not None:
            try:
                tracker.on_start(result[0])
                if shutdown:
                    shutdown.queue_started()
            except Exception:
                logger.exception(f"{LOG_PREFIX} Failed to record the start of a prompt")
        return result

    def task_done(item_id, *args, **kwargs):
        # Record before handing over to ComfyUI: its task_done announces the queue change to the
        # frontend, and the node has to find the new stats when it asks for them in response.
        try:
            item = prompt_queue.currently_running.get(item_id)
            if item is not None:
                status = kwargs.get("status", args[1] if len(args) > 1 else None)
                success = bool(getattr(status, "completed", False))
                running, pending = current_queue(prompt_queue)
                running = [other for other in running if other[1] != item[1]]
                done = tracker.on_done(item, success, len(running) + len(pending))
                if shutdown and done["batch"]:
                    shutdown.queue_finished()
                # Flushed, so the line also shows up right away when the console is redirected to a file.
                print(f"{LOG_PREFIX} {_console_line(done, tracker.snapshot(running, pending), tracker.clock())}", flush=True)
        except Exception:
            logger.exception(f"{LOG_PREFIX} Failed to record the end of a prompt")
        return original_task_done(item_id, *args, **kwargs)

    prompt_queue.get = get
    prompt_queue.task_done = task_done
    return True


def setup(server):
    """Start timing the queue of this server and add the routes used by js/queue_eta.js."""
    from aiohttp import web
    import folder_paths

    tracker = QueueEtaTracker(os.path.join(folder_paths.get_user_directory(), STATS_FILENAME))
    shutdown = ShutdownSwitch(notify=server.queue_updated)
    if not install_hooks(server.prompt_queue, tracker, shutdown):
        # The node pack is installed twice, the copy that loaded first does the work
        # (registering the same routes a second time would stop ComfyUI from starting).
        logger.warning(f"{LOG_PREFIX} The queue is already being timed by another copy of this node pack")
        return

    def snapshot():
        running, pending = current_queue(server.prompt_queue)
        data = tracker.snapshot(running, pending)
        data["shutdown"] = shutdown.state()
        return data

    async def json_body(request):
        # JSON only: a browser cannot send that to another site without asking first (CORS).
        if request.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType(text="Expected application/json")
        try:
            data = await request.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @server.routes.get("/brekel/queue_eta")
    async def get_queue_eta(request):
        return web.json_response(snapshot())

    @server.routes.post("/brekel/queue_eta/names")
    async def name_queue_eta(request):
        data = await json_body(request)
        tracker.set_names(data.get("names"))
        return web.json_response(snapshot())

    @server.routes.post("/brekel/queue_eta/shutdown")
    async def shutdown_queue_eta(request):
        data = await json_body(request)
        armed = data.get("armed") is True
        # Switching off can run 'shutdown /a', which must not hold up the web server.
        await asyncio.get_running_loop().run_in_executor(None, shutdown.set_armed, armed)
        print(f"{LOG_PREFIX} Shut down when the queue is done: {'on' if armed else 'off'}", flush=True)
        return web.json_response(snapshot())

    @server.routes.post("/brekel/queue_eta/reset")
    async def reset_queue_eta(request):
        data = await json_body(request)
        signature = data.get("sig")
        forgotten = tracker.reset(signature if isinstance(signature, str) and signature else None)
        print(f"{LOG_PREFIX} Stats reset, {forgotten} workflow(s) forgotten", flush=True)
        # Let the other open tabs pick up the change too.
        server.queue_updated()
        return web.json_response(snapshot())


if PromptServer.instance is not None:
    setup(PromptServer.instance)


# --- QUEUE ETA CLASS ---
class BrekelQueueETA:
    """
    Display-only node: it has no inputs or outputs and never runs. Its panel is drawn by
    js/queue_eta.js from the stats the tracker above collects.
    """

    @classmethod
    def INPUT_TYPES(s):
        return {"required": {}}

    # --- Node configuration for ComfyUI ---
    CATEGORY = "Brekel"
    FUNCTION = "noop"
    RETURN_TYPES = ()
    DESCRIPTION = (
        "Shows how many prompts are left in the queue, the estimated time left and the time of arrival. "
        "The estimate is learned from how long previous runs of each workflow took. "
        "It does not need to be connected to anything."
    )

    def noop(self):
        return ()


# --- ComfyUI Node Registration ---
NODE_CLASS_MAPPINGS = {"BrekelQueueETA": BrekelQueueETA,}
NODE_DISPLAY_NAME_MAPPINGS = {"BrekelQueueETA": "Brekel Queue ETA",}
