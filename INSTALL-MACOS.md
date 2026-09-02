# Installing and running on macOS

This is a practice tool for the Engineering Mathematics course. You run it on
your **own machine**; there is no server to log into.

**What it does:** generates unlimited practice problems (ODEs, Laplace
transforms, Fourier series, 2×2 linear systems) with worked solutions that are
verified by SymPy before you ever see them, plus six interactive
signal-processing demos that make sound in your browser.

**What it does not do:** there are no accounts, no passwords, and no database.
It does not record what you do and it never sends anything over the network.
Once it is installed it works with your Wi-Fi turned off.

> ## ⚠️ Read this before anything else: do not use Safari
>
> The interactive demos are **not supported on Safari**, and that is a
> deliberate decision rather than a bug we have not got round to. Safari is
> the default browser on your Mac, so this is the single thing most likely to
> waste your time here.
>
> **Install Chrome or Firefox and open the site in one of those.** The
> practice pages work fine in Safari; the demos are the problem. Details in
> *Browser support* below.

---

## Before you start

You need **Python 3.10 or newer** and **git**.

macOS ships with a `python3`, but which version depends on your macOS release,
and on a fresh machine the first `python3` or `git` command pops up a dialog
offering to install the Xcode Command Line Tools. Check what you have:

```bash
python3 --version
git --version
```

If the dialog appears, click **Install** and wait (it is a few hundred MB),
then run the commands again.

If `python3 --version` prints 3.9 or lower, install a newer one. The usual way
is [Homebrew](https://brew.sh):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12
```

Alternatively download an installer from <https://www.python.org/downloads/>.
Either works; you only need one.

> **Apple Silicon (M1/M2/M3/M4) is fine.** Every dependency ships an arm64
> wheel, so nothing is compiled during the install and Rosetta is not
> involved.

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

> **A macOS-specific trap:** if you double-click the ZIP in Finder, it unpacks
> into `~/Downloads/engmath-practice`. That is fine, but folders under
> `~/Downloads` are subject to Gatekeeper's quarantine and some editors will
> nag about it. Moving the folder somewhere like `~/Projects` avoids the
> nagging. It does not affect whether the program runs.

## 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now start with `(.venv)`. That tells you the next command
installs into this folder and not into your system Python.

> **Why bother?** Homebrew's Python refuses to install packages into itself
> (PEP 668) and stops with `error: externally-managed-environment`. The
> virtual environment is the supported way round it — not
> `--break-system-packages`, which does what it says.
>
> If you installed Python 3.12 from Homebrew and `python3` still points at
> Apple's older one, use `python3.12 -m venv .venv` instead.

## 3. Install the dependencies

```bash
pip install -r requirements.txt
```

This pulls in FastAPI, uvicorn, Jinja2 and SymPy. SymPy is the big one
(about 40 MB); the whole install takes a minute or two on a normal connection.

## 4. Run it

```bash
uvicorn app.main:app
```

You should see:

```
INFO:     Started server process [12345]
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Now open **<http://127.0.0.1:8000>** — **in Chrome or Firefox**, not Safari.
From the terminal, to open it in Chrome specifically:

```bash
open -a "Google Chrome" http://127.0.0.1:8000
```

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

If you find yourself typing that a lot, put this in your `~/.zshrc` (adjust
the path):

```bash
alias engmath='cd ~/Projects/engmath-practice && source .venv/bin/activate && uvicorn app.main:app'
```

### Updating

```bash
git pull
source .venv/bin/activate
pip install -r requirements.txt   # only needed if requirements.txt changed
```

### Removing it

Delete the folder. That is all — nothing was installed anywhere else, no
launch agents were registered, and no files were written outside it.

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
>
> On a Mac, also check that your output device is what you think it is:
> if AirPods are connected, the sound goes there, and their frequency
> response makes the aliasing demo much less convincing.

---

## Browser support

**Chrome and Firefox are supported. Safari is not.**

This deserves an explanation rather than just a rule, because Safari does not
obviously fail. The demos use `AudioWorklet`, `PeriodicWave` and
`OfflineAudioContext`, and **modern Safari has all three** — so a
feature-detection check passes, and then the pages behave differently anyway.
That is the worst kind of unsupported: it half works.

So the demo pages check twice, above the controls. A **red** message means an
API the page needs is genuinely missing — it will not work. An **amber**
message means the browser has everything but is not an engine we have tested,
which is what Safari gets: the page may be subtly wrong without saying so, and
we are not claiming it is right.

If you only have Safari, the **practice pages work fine** — it is only the
six demos that are affected.

> One thing that trips people up: `AudioWorklet` only works in a *secure
> context*, which normally means HTTPS. **`http://127.0.0.1` and
> `http://localhost` count as secure contexts**, which is why plain HTTP is
> fine here. It would not be fine if you served this to another machine.

---

## Troubleshooting

**`command not found: uvicorn`**
You forgot `source .venv/bin/activate`, or you are in a different Terminal tab
than the one where you activated it. The prompt should show `(.venv)`.

**`error: externally-managed-environment`**
You are installing outside the virtual environment. Go back to step 2.

**`xcrun: error: invalid active developer path`**
The Command Line Tools are missing or were broken by a macOS upgrade. Run:

```bash
xcode-select --install
```

**`ModuleNotFoundError: No module named 'app'`**
You are not in the project folder. `cd` to the directory that contains
`app/` and `requirements.txt`, and run `uvicorn` from there.

**`[Errno 48] Address already in use`**
Something else is on port 8000 — quite possibly a copy of this that you forgot
to stop. Either stop it, or use another port:

```bash
uvicorn app.main:app --port 8123
```

Then open <http://127.0.0.1:8123>.

> If you ever try port **5000**, expect trouble: macOS uses it for AirPlay
> Receiver. Port 8000 and 8123 are fine.

**The page loads but the mathematics is raw LaTeX like `\frac{1}{2}`**
The KaTeX files under `app/static/vendor/` did not load. This usually means
the download or the clone was incomplete. Re-clone, or check that
`app/static/vendor/katex/katex.min.js` exists and is not empty.

**A demo page is silent**
Press **Start sound** first — nothing plays before you do. Then check
System Settings → Sound for the output device, and make sure the browser tab
is not muted.

**A demo page shows an amber message above the controls**
You are in Safari or another WebKit browser. Switch to Chrome or Firefox.
(The demos are desktop-only by design, so a phone or tablet is not an
alternative.)

**"Could not generate a valid problem this time. Please press Generate again."**
This is honest rather than broken: the generator produces a random problem and
then checks it with SymPy, and occasionally it cannot find one that passes
within its attempt budget. Press Generate again. If one particular topic does
it repeatedly, tell your instructor — that is a real bug in that topic's
parameter ranges.

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
