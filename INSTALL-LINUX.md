# Installing and running on Linux

This is a practice tool for the Engineering Mathematics course. You run it on
your **own machine**; there is no server to log into.

**What it does:** generates unlimited practice problems (ODEs, Laplace
transforms, Fourier series, 2×2 linear systems) with worked solutions that are
verified by SymPy before you ever see them, plus six interactive
signal-processing demos that make sound in your browser.

**What it does not do:** there are no accounts, no passwords, and no database.
It does not record what you do and it never sends anything over the network.
Once it is installed it works with your Wi-Fi turned off.

---

## Before you start

You need **Python 3.10 or newer** and **git**. Check what you have:

```bash
python3 --version
git --version
```

If `python3 --version` prints 3.9 or lower, or the command is not found,
install a newer Python with your package manager:

| Distribution | Command |
|---|---|
| Debian / Ubuntu / Mint | `sudo apt install python3 python3-venv python3-pip git` |
| Fedora / RHEL | `sudo dnf install python3 python3-pip git` |
| Arch / Manjaro | `sudo pacman -S python python-pip git` |
| openSUSE | `sudo zypper install python3 python3-pip git` |

> **Debian and Ubuntu users: do not skip `python3-venv`.** It is a separate
> package on those distributions, and without it step 2 below fails with
> `The virtual environment was not created successfully`. The error message
> does tell you what to install, but it appears several lines down.

You also need a browser. **Use Chrome or Firefox.** The interactive demos are
not supported on Safari or on any WebKit-based browser (GNOME Web, for
example) — see *Browser support* below.

---

## 1. Get the code

```bash
git clone https://github.com/wangc86/engmath-practice.git
cd engmath-practice
```

If you would rather not
use git, download the ZIP from <https://github.com/wangc86/engmath-practice>, unpack it, and `cd` into the
folder — everything below works the same way, except that you cannot use
`git pull` to update later.

## 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now start with `(.venv)`. That tells you the next command
installs into this folder and not into your system Python.

> **Why bother?** Because on Debian, Ubuntu and Fedora, installing packages
> into the system Python is blocked on purpose (PEP 668). If you try, pip
> stops with `error: externally-managed-environment`. The virtual environment
> is the supported way round it — not `--break-system-packages`, which does
> what it says.

## 3. Install the dependencies

```bash
pip install -r requirements.txt
```

This pulls in FastAPI, uvicorn, Jinja2 and SymPy. SymPy is the big one
(about 40 MB); the whole install takes a minute or two on a normal connection.

Nothing here needs a C compiler, so there is no build step that can fail.

## 4. Run it

```bash
uvicorn app.main:app
```

You should see:

```
INFO:     Started server process [12345]
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Now open **<http://127.0.0.1:8000>** in Chrome or Firefox.

To check the server is really up without leaving the terminal:

```bash
curl http://127.0.0.1:8000/healthz
# {"status":"ok"}
```

Press **Ctrl+C** in the terminal to stop it.

---

## Using it afterwards

Every time you want to use it again, from the project folder:

```bash
source .venv/bin/activate
uvicorn app.main:app
```

Only step 4 — the virtual environment and the packages stay installed.

If you find yourself typing that a lot, put this in your `~/.bashrc` (adjust
the path):

```bash
alias engmath='cd ~/engmath-practice && source .venv/bin/activate && uvicorn app.main:app'
```

### Updating

```bash
git pull
source .venv/bin/activate
pip install -r requirements.txt   # only needed if requirements.txt changed
```

### Removing it

Delete the folder. That is all — nothing was installed anywhere else, no
services were registered, and no files were written outside it.

---

## What is on the two pages

**Practice** (`/`) — pick a topic and a difficulty, press **Generate**.
The topics are grouped by course week, so the material for this week's lecture
is under this week's heading.

The answer and the worked solution both start hidden. That is deliberate:
solve it on paper first, then press **Show Answer** to compare, and
**Show Solution Steps** only if you want to see how it is done.

**Demos** (`/demos`) — six interactive pages that make sound: aliasing,
spectra and windowing, Fourier series by additive synthesis, convolution,
pulse width and the time–frequency trade-off, and poles and zeros of digital
filters. They are also grouped by course week.

> **The demos play audio.** Each one has a **Start sound** button, because
> browsers do not let a page make noise until you press something.
> **Use headphones and start with the volume low.** The pole–zero page in
> particular can produce a loud resonance if you drag a pole close to the
> unit circle — the page limits the output, but the limiter cannot undo
> a volume knob that is already at maximum.

---

## Browser support

**Chrome and Firefox are supported. Safari and other WebKit browsers are not.**

The demos use `AudioWorklet`, `PeriodicWave` and `OfflineAudioContext`.
Safari has all three, so a capability check passes — and then the pages behave
differently anyway. Rather than pretend, the demo pages detect the engine and
show a warning.

The demo pages check twice. A **red** message above the controls means your
browser is genuinely missing an API the page needs — it will not work. An
**amber** message means the browser has everything but is not an engine we
have tested, so the page may be subtly wrong without saying so. Either way,
switch to Chrome or Firefox.

> One thing that trips people up: `AudioWorklet` only works in a *secure
> context*, which normally means HTTPS. **`http://127.0.0.1` and
> `http://localhost` count as secure contexts**, which is why plain HTTP is
> fine here. It would not be fine if you served this to another machine.

---

## Troubleshooting

**`command not found: uvicorn`**
You forgot `source .venv/bin/activate`, or you are in a different terminal
window than the one where you activated it. The prompt should show `(.venv)`.

**`error: externally-managed-environment`**
You are installing outside the virtual environment. Go back to step 2.

**`ModuleNotFoundError: No module named 'app'`**
You are not in the project folder. `cd` to the directory that contains
`app/` and `requirements.txt`, and run `uvicorn` from there.

**`[Errno 98] Address already in use`**
Something else is on port 8000 — quite possibly a copy of this that you
forgot to stop. Either stop it, or use another port:

```bash
uvicorn app.main:app --port 8123
```

Then open <http://127.0.0.1:8123>.

**The page loads but the mathematics is raw LaTeX like `\frac{1}{2}`**
The KaTeX files under `app/static/vendor/` did not load. This usually means
the download or the clone was incomplete. Re-clone, or check that
`app/static/vendor/katex/katex.min.js` exists and is not empty.

**A demo page is silent**
Press **Start sound** first — nothing plays before you do. If it is still
silent, check that your system is not muted and that the browser tab is not
muted (right-click the tab in Chrome).

**"Could not generate a valid problem this time. Please press Generate again."**
This is honest rather than broken: the generator produces a random problem and
then checks it with SymPy, and occasionally it cannot find one that passes
within its attempt budget. Press Generate again. If one particular topic does
it repeatedly, tell your instructor — that is a real bug in that topic's
parameter ranges.

**Everything is slow**
Generating a problem runs SymPy and takes roughly 0.1–0.5 seconds; the Fourier
topics are the slowest because their verification gate is four layers deep.
That is expected. A blank page for ten seconds is not — report it.

---

## Optional: run the tests

If you want to see what is being checked, or you have changed something:

```bash
source .venv/bin/activate
pytest
```

There are about 1300 tests and the full run takes 10–12 minutes, most of it
SymPy verifying generated problems. To check just the web pages:

```bash
pytest tests/test_web.py -q
```

---

## Where things are

| Path | What it is |
|---|---|
| `app/generator/` | The problem generators. This is where the real work is. |
| `app/static/demos/` | The interactive demos (plain JavaScript, no build step). |
| `app/curriculum.py` | Which topic belongs to which course week. |
| `PLAN.md` | The design document, including every decision and why. |
| `README.md` | Project overview and developer notes. |
| `COLLABORATION-NOTES.md` | How this project was built with an AI assistant. |

If you want to add a topic of your own, `README.md` has a section called
「新增一個題型」 with a worked skeleton. The developer documentation is in
Traditional Chinese; the user interface and the generated problems are in
English.
