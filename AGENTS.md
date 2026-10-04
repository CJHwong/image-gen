# AGENTS.md

Working rules for a coding agent in this repo. The layers, the naming rule and the wiring of a backend are in [studio/ARCHITECTURE.md](studio/ARCHITECTURE.md). This file holds the method: what to prove, and how.

## The GPU is shared

One model fits in memory at a time. A second job on the GPU makes every timing wrong, and two models can run the machine out of memory.

1. Before a GPU run, check port 8765, the default studio port. If a server runs there, ask the user to stop it. Never stop it yourself.
2. Run your own server on another port. Stop it when you finish.
3. Run one GPU job at a time. If a timing ran next to another GPU job, discard it and measure again.
4. If a change touches only the page, run `uv run studio --stub --port <port>`. The stub keeps each backend's form and fakes the engine, so it uses no GPU and the user's server can keep running. A change to a backend or its engine still needs the real model. The server reads `page.html` once at start, so restart the stub after an edit to the page, or it keeps serving the old one.
5. Run the real check against the tree you verified, and nothing else. Commit and push it, then on the office machine `git reset --hard origin/<branch>`, because `git checkout` on a branch that is already checked out does not advance it. Confirm the served files' digests match the ones you measured. Two runs died against a revision that was never under test.
6. On the office machine, `uv` must be on the PATH of the server **and of the children it spawns**: `export PATH=/opt/homebrew/bin:$PATH`. Starting the server with the absolute path to `uv` works and leaves the edit engine unable to find it, which fails as `env: uv: No such file or directory`. That reads like a broken edit rather than a broken environment, and it cost three runs.
7. Never pipe a check through a filter when you need its status. `| grep` makes the exit code the filter's, so a traceback reads as a pass.
8. Take the digest of what you measured at the same moment as the measurement, or bracket the run with it. A digest sampled later is not evidence about the bytes under test. One such digest belonged to a revision another worker's mutation script had rewritten, and the difference was reported as a flaky check that did not exist.
9. The whole web/ tree is CPU work. Slices of it, and the UI suite, need no GPU: only `verify_page.py` does, because it generates and edits real images and asserts on their pixels.

## Backend flow

Run this flow when you add a backend. Also run it when you change one: its capabilities, its engine code, its weights, or the pinned mflux commit. For a change, run the steps the change touches, and always run steps 8 to 12.

1. **Test the engine primitives.** Read the engine code at the pinned commit. In a short script, test how it loads, how long the load takes, and whether the step callback fires. Also test whether it takes a reference as a PIL image, so that no image goes to disk. Test each primitive before you design around it.
2. **Declare the capabilities** in `gateways/<id>/capabilities.py`.
   - Take the defaults for steps, guidance and size from this model's own recommended settings. Do not copy them from another backend.
   - An edit mode defaults its size to "match", so the output keeps the reference's size.
   - Put every size on the 16-pixel grid. Keep its named ratio within 1%. Add the new `SIZES` to `test_every_size_keeps_its_named_ratio_on_the_16_pixel_grid` in `tests/l3_interface_adapters/gateways/qwen21/test_capabilities.py`.
   - Leave out Looks and templates until step 5 proves them on this model.
3. **Measure the cost.** With the GPU free, measure the seconds per step for each mode at three sizes: about 0.25, 0.6 and 1 MP. For an edit, measure with 1 reference and with the maximum. Fit `step_cost`, `exponent` and `overhead` for the `Estimate`. Put the measured table in a comment next to it, with the machine and the quantization.
4. **Spike before you build an engine feature**, such as real batching. Measure it on the real engine first, and build it only if it wins. Write the result in the README section "Why it looks like this", whether it wins or not. For example, a batched flux2 run was 2 to 8% slower per image, so a batch stays a chain of single runs.
5. **Test the prompt aids on this model.** Sample; do not run every option.
   - Use one seed, 768 x 768, 20 steps and the model's own guidance. Put each image next to the bare prompt.
   - Take two or three options per Look row, the ones most likely to behave differently on this model. Take each template with its first fill-in.
   - Make one contact sheet per row, and look at every image.
   - Keep only the options that visibly work. Pick them with `pick_looks` in the backend's capabilities, and write the verdicts in `gateways/PROMPTS.md`.
   - Test an avoid part against a neutral negative at the same guidance, such as "low quality". Do not use a blank negative as the control: on qwen21, a blank negative turns true CFG off, so the two images differ in more than the avoid text. Keep an avoid part only if it wins on more than one seed, because it doubles the time of each image.
   - Before a full run, tell the user the image count and the time, and wait for approval.
6. **Wire it in.** Follow "Add a backend" in ARCHITECTURE.md. Add the package to the `backends-independent` contract in `.importlinter`. Then prove that the contract can fail: add one import across adapters, see `lint-imports` fail, and remove the import.
7. **Test it.**
   - Put the test at the mirrored path under `tests/`, beside the module it covers. Mock the engine, so the test needs no model.
   - Write unit tests for how the form maps to the engine arguments.
   - Write one `live` test that loads the real weights.
   - Give each fix a test, then remove the fix once and watch that test fail.
   - Run a mutation proof against a copy of the tree, never the shared page directory. Another
     worker may be testing against that tree at the same moment, and a mutation running on it
     looks exactly like a flaky check in the report you read next.
   - Serve the copy from inside the copy. Start the studio with
     `cd <copy> && uv run --project <repo> python -c "from studio.__main__ import main; main()"`,
     and never with the `studio` console script. The console script puts its own `bin` directory
     on `sys.path`, so it imports the repo's `studio` and serves the unmutated tree. A green run
     then certifies the very thing it failed to test. Fetch the mutated file off the running
     server first, and read the result only once the mutation is in what it serves.
8. **Pass the gates.**
   - Run `prek run --all-files`. It runs ruff, ty, import-linter and the secret scan. `--all-files` skips untracked files; while files are untracked, pass `--files $(git ls-files -co --exclude-standard)` instead.
   - Run `uv run pytest`, then `uv run pytest -m live -k <id>`. The first one fails when the statement or branch coverage of `studio/` drops below 100%.
9. **Prove it with real runs.** A green test is a gate, not proof.
   - `tests/e2e/verify_capabilities.py`, which needs no GPU.
   - `tests/e2e/verify_backends.py`, against `uv run studio --port <port> --backend <id>`.
   - `tests/e2e/verify_page.py` and `tests/e2e/verify_storage.py`, if the page changed.
   - `tests/e2e/verify_ui.py`, against `uv run studio --stub --port <port>`, if a control on the page changed. It needs no GPU.
   - In the browser, one generate, one edit, and one cancel during a run.
10. **Get a review.** Get an independent code review of the change. Fix each finding the way step 7 says, then run steps 8 and 9 again.
11. **Update the docs.**
    - In the README: the models table, the weight setup, and the license. The weight setup is a recipe that downloads to the default `model_dir`.
    - The backend's section in `studio.toml`.
    - ARCHITECTURE.md, if a rule changed.
12. **Clean up.** Delete the scratch scripts and images. Stop your server and your background jobs. Commit only when the user says so. Commit messages follow Conventional Commits, with body lines of 100 characters at most.
