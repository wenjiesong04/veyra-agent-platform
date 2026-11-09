# Veyra Agent Platform

**Build and run Agents and Workflows in a local AI studio.**

Describe a task in your own words, review what Veyra proposes, and edit the
Agent or Workflow in Studio. Commit a version before running it with your own
inputs, then inspect the results and execution records.

![English Veyra Studio showing an example gift-packaging Workflow draft](docs/images/gift-studio-en.jpg)

The screenshot shows an example draft in the English Studio. The walkthrough
uses recorded Workflow screens and an existing image candidate. The parent
run failed, and the candidate still needs review.
[Watch the 40-second walkthrough](web/apps/community/public/showcase/veyra-gift-tour.mp4) ·
[Read the case notes](docs/SHOWCASE_MEDIA.md)

## What you can do

- **Build in Desktop.** Create Projects, describe tasks in Chat, and review,
  edit, test, and version your Agents and Workflows in Studio. Project files,
  Builder conversations, and Run records are stored locally. Configured model
  providers and tools may connect to external services.
- **Share through the Community website.** Export an Agent in Desktop, then
  sign in on the website to preview and publish the file. The website accepts
  Agent definitions and Plugin Packs. Downloaded packages are imported and
  inspected in Desktop. [Community guide](docs/COMMUNITY_WEBSITE.md)
- **Inspect what ran.** Open the execution record to see the version, inputs,
  outputs, and verification status. An execution can finish before its
  result has been verified.

## Quick start

Use Conda, Python 3.11, and Node.js 24 with npm. Run these commands from the
repository root. Create the Conda environment once and reuse it on later runs.

```sh
conda env create -f environment.yml
conda activate veyra-agent-platform
make install PYTHON=python
npm --prefix web ci
```

### Preview the website

Run `npm --prefix web run dev:community` and open
[the local product showcase](http://127.0.0.1:5174). The demo and project
documentation are available before signing in.

### Start the desktop workspace

Start each service in its own terminal from the repository root. Activate
`veyra-agent-platform` in each Python terminal.

| Service | Command | Local address |
| --- | --- | --- |
| Local API | `veyra-local` | `127.0.0.1:8771` |
| Community API | `make migrate-community PYTHON=python && veyra-community` | `127.0.0.1:8772` |
| Desktop interface | `npm --prefix web run dev:desktop` | `127.0.0.1:5173` |
| Community website | `npm --prefix web run dev:community` | `127.0.0.1:5174` |

Open [Desktop](http://127.0.0.1:5173) and sign in with an account on the
Community API you started. To create an account, set the SMTP variables shown
in [.env.example](.env.example) in the Community API terminal before starting
the service. Configure a model provider in Desktop Settings before asking
Builder to generate an Agent or running a model-backed task.

## Build and validate

```sh
make check PYTHON=python
npm --prefix web run typecheck
npm --prefix web test
npm --prefix web run build
```

The macOS arm64 desktop package is a release candidate. The repository contains
the source and build instructions, and CI checks the sidecar, application
signature, and DMG. [Desktop packaging guide](docs/desktop_packaging.md)

## Project documentation

- [Community publishing and desktop import](docs/COMMUNITY_WEBSITE.md)
- [Desktop build and packaging](docs/desktop_packaging.md)
- [Community deployment and storage](docs/community_production_storage.md)
