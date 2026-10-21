"""Check draft storage races in a browser against a stub server."""

import sys

from playwright.sync_api import sync_playwright

with sync_playwright() as tool:
    browser = tool.chromium.launch()
    page = browser.new_page()
    page.route("**/draft-check", lambda route: route.fulfill(body="<html></html>", content_type="text/html"))
    page.goto("http://127.0.0.1:" + sys.argv[1] + "/draft-check")
    results = page.evaluate("""async () => {
      let configure;
      document.addEventListener('drafts-ready', event => { configure = event.detail.configure; });
      const storage = await import('/page/lib/drafts.js');
      await storage.clearDrafts();
      let backend = 'first';
      let inputs = {prompt: 'first words'};
      const controller = configure({clientId: 'client', keeping: () => true, blocked: () => false,
        backend: () => backend, snapshot: () => inputs, restore: (workspace, value) => { inputs = value; },
        empty: () => ({prompt: ''}), notify: (kind, message) => { throw new Error(message); }});
      while (controller.loading()) await new Promise(resolve => setTimeout(resolve, 10));
      const second = {id: 'second-draft', updatedAt: 1, inputs: {prompt: 'second words'}};
      await storage.saveDraft('image:second', second);
      controller.changed('image'); await controller.flushed();
      if (controller.pause) controller.pause('image');
      backend = 'second';
      controller.changed('image');
      await controller.restore('image'); await controller.flushed();
      const modelSafe = inputs.prompt === 'second words';
      inputs = {prompt: 'new submission'};
      const submission = controller.submit('image'); await controller.flushed();
      controller.observe([{id: 'old-job', workspace: 'image', client_id: 'client', started_at: 9,
        status: 'succeeded', settings: {draft_id: 'old-draft'}}]);
      await controller.flushed(); await new Promise(resolve => setTimeout(resolve, 20));
      const oldSafe = inputs.prompt === 'new submission';
      controller.observe([{id: 'new-job', workspace: 'image', client_id: 'client', started_at: 10,
        status: 'succeeded', settings: {draft_id: submission}}]);
      await controller.flushed(); await new Promise(resolve => setTimeout(resolve, 20));
      const cleared = inputs.prompt === '';
      const bytes = new Blob(['reference bytes'], {type: 'audio/wav'});
      await storage.saveDraft('bytes', {id: 'new', updatedAt: 4, inputs: {bytes}});
      const stale = await storage.saveDraft('bytes', {id: 'old', updatedAt: 2});
      const wrong = await storage.saveDraft('bytes', {id: 'clear', updatedAt: 5}, 'old');
      const stored = await storage.loadDraft('bytes');
      const atomic = !stale && !wrong && stored.id === 'new' && await stored.inputs.bytes.text() === 'reference bytes';
      await storage.clearDrafts();
      return {modelSafe, oldSafe, cleared, atomic, removed: await storage.loadDraft('bytes') === null};
    }""")
    for name, passed in results.items():
        assert passed, (name, results)
        print("PASS " + name, flush=True)
    browser.close()
