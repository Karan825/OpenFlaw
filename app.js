/**
 * OpenFlaw — Pure Monochrome Frontend Logic
 * Interactive ReAct Loop Simulator, Tool Registry, and Code Clipboard
 */

document.addEventListener('DOMContentLoaded', () => {
  initSimulator();
  initToolTabs();
  initQuickstartTabs();
  initCopyButtons();
});

/* =========================================================================
   TOOL REGISTRY DATA
   ========================================================================= */
const TOOLS_DATA = {
  repomap: {
    title: 'Repo Map Indexer',
    file: 'worker/src/agent/tools/repo_map.py',
    type: 'AST SYMBOL GRAPH',
    description: 'Constructs an in-memory Abstract Syntax Tree (AST) graph of the codebase using Tree-Sitter. Generates hierarchical symbol outlines so the LLM knows all function definitions, class signatures, and imported modules in under 500 tokens.',
    code: `class RepoMap:
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)
        self.parser = get_tree_sitter_parser()

    def generate_skeleton(self, max_tokens: int = 1024) -> str:
        """Parses AST to build rank-ordered symbol signatures."""
        symbols = self._extract_ast_symbols()
        return self._render_compact_hierarchy(symbols)`
  },
  ripgrep: {
    title: 'Ripgrep Searcher',
    file: 'worker/src/agent/tools/ripgrep.py',
    type: 'HIGH-SPEED REGEX SEARCH',
    description: 'Executes native C-speed ripgrep queries across the repository to locate stack traces, symbol usages, exception origins, and test assertions in milliseconds.',
    code: `class RipgrepTool:
    def search(self, pattern: str, case_sensitive: bool = False, max_results: int = 20):
        """Runs ripgrep regex pattern matching within the sandbox filesystem."""
        cmd = ["rg", "--json", "-m", str(max_results), pattern]
        output = subprocess.check_output(cmd, cwd=self.sandbox_path)
        return self._format_json_matches(output)`
  },
  fileeditor: {
    title: 'Exact File Editor',
    file: 'worker/src/agent/tools/file_editor.py',
    type: 'DETERMINISTIC PATCHER',
    description: 'Executes atomic substring replacements and diff insertions. Verifies exact pre-patch code content before modifying lines to prevent hallucinated line offsets or corrupted files.',
    code: `class FileEditor:
    def replace_block(self, file_path: str, target_snippet: str, replacement: str):
        """Atomic replacement with content validation."""
        content = self._read_file(file_path)
        if target_snippet not in content:
            raise FileEditError(f"Target snippet not found in {file_path}")
        new_content = content.replace(target_snippet, replacement, 1)
        self._write_file(file_path, new_content)`
  },
  terminal: {
    title: 'Sandboxed Terminal',
    file: 'worker/src/agent/tools/terminal.py',
    type: 'E2B VM SHELL RUNNER',
    description: 'Runs non-interactive shell commands inside the Firecracker microVM. Streams stdout and stderr back to the ReAct agent loop with execution timeout guards.',
    code: `class SandboxedTerminal:
    def run(self, cmd: str, timeout: int = 30):
        """Executes terminal commands strictly inside E2B Sandbox."""
        execution = self.sandbox.commands.run(cmd, timeout=timeout)
        return {
            "exit_code": execution.exit_code,
            "stdout": execution.stdout,
            "stderr": execution.stderr
        }`
  },
  diffguard: {
    title: 'Diff & Safety Guard',
    file: 'worker/src/safety/diff_guard.py',
    type: 'SECURITY FILTER',
    description: 'Validates all proposed edits against security policies: rejects alterations to CI workflows, prevents secrets/keys from being written, and denies modifications outside the target repository tree.',
    code: `class SafetyGuard:
    BLOCKED_PATTERNS = [r"\.env", r"\.github/workflows/.*", r"id_rsa"]
    
    def validate_diff(self, diff: str) -> bool:
        """Enforces write boundaries and prevents secret leaks."""
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, diff):
                raise SecurityViolation(f"Modification to protected path: {pattern}")
        return True`
  }
};

/* =========================================================================
   SIMULATION SCENARIOS
   ========================================================================= */
const SIM_SCENARIOS = {
  zero_division: {
    title: 'Issue #104: ZeroDivisionError in calculate_metrics()',
    steps: [
      { step: 1, time: '00:00:01', tag: 'WEBHOOK', tagClass: 'term-webhook', text: 'Ingested webhook event: issue_comment.created on Karan825/OpenFlaw#104 (@agent fix)' },
      { step: 2, time: '00:00:02', tag: 'SANDBOX', tagClass: 'term-sandbox', text: 'Spun up isolated E2B microVM [id: vm-8f902c] (ubuntu-22.04, 2 vCPU, 2GB RAM)' },
      { step: 3, time: '00:00:03', tag: 'AST_MAP', tagClass: 'term-ast', text: 'Tree-Sitter parsed repository: 18 files indexed, 94 AST symbols mapped' },
      { step: 4, time: '00:00:04', tag: 'REACT', tagClass: 'term-react', text: 'THOUGHT: Issue states "ZeroDivisionError when total_samples == 0". Locating calculate_metrics() definition.' },
      { step: 4, time: '00:00:05', tag: 'TOOL_CALL', tagClass: 'term-ast', text: 'ACTION: ripgrep.search("def calculate_metrics")' },
      { step: 4, time: '00:00:06', tag: 'OBSERVE', tagClass: 'term-info', text: 'OBSERVATION: Found in src/analytics/metrics.py:42: def calculate_metrics(success_count, total_samples):' },
      { step: 4, time: '00:00:08', tag: 'REACT', tagClass: 'term-react', text: 'THOUGHT: If total_samples is 0, returning rate 0.0 prevents division by zero. Generating patch...' },
      { step: 4, time: '00:00:10', tag: 'PATCH', tagClass: 'term-patch', text: 'ACTION: file_editor.replace_block(src/analytics/metrics.py)', diff: true, diffContent: `--- a/src/analytics/metrics.py\n+++ b/src/analytics/metrics.py\n@@ -42,3 +42,5 @@\n def calculate_metrics(success_count, total_samples):\n+    if total_samples == 0:\n+        return 0.0\n     return success_count / total_samples` },
      { step: 5, time: '00:00:12', tag: 'SAFETY', tagClass: 'term-info', text: 'SAFETY_GUARD: Validating git diff. 0 protected files touched. 0 secret leaks detected.' },
      { step: 6, time: '00:00:14', tag: 'VERIFY', tagClass: 'term-verify', text: 'ACTION: terminal.run("pytest tests/test_metrics.py -v")' },
      { step: 6, time: '00:00:17', tag: 'PYTEST', tagClass: 'term-info', text: 'PASSED: 12/12 tests passed (100% test coverage on modified lines).' },
      { step: 7, time: '00:00:20', tag: 'SUCCESS', tagClass: 'term-success', text: 'PR CREATED: Opened Pull Request #105 "fix: prevent ZeroDivisionError when total_samples is 0" with full ReAct logs.' }
    ]
  },
  jwt_expiry: {
    title: 'Issue #119: JWT Expired Token Bypass Vulnerability',
    steps: [
      { step: 1, time: '00:00:01', tag: 'WEBHOOK', tagClass: 'term-webhook', text: 'Ingested webhook event: issues.labeled "security-flaw" on OpenFlaw#119' },
      { step: 2, time: '00:00:02', tag: 'SANDBOX', tagClass: 'term-sandbox', text: 'Spun up isolated E2B microVM [id: vm-31ac7e] with network egress restrictions' },
      { step: 3, time: '00:00:03', tag: 'AST_MAP', tagClass: 'term-ast', text: 'Mapped auth controllers and token validation interceptors in src/security/' },
      { step: 4, time: '00:00:05', tag: 'REACT', tagClass: 'term-react', text: 'THOUGHT: Inspecting jwt.decode options in src/security/jwt_validator.py.' },
      { step: 4, time: '00:00:07', tag: 'TOOL_CALL', tagClass: 'term-ast', text: 'ACTION: ripgrep.search("verify_exp")' },
      { step: 4, time: '00:00:09', tag: 'PATCH', tagClass: 'term-patch', text: 'ACTION: file_editor.replace_block(src/security/jwt_validator.py)', diff: true, diffContent: `--- a/src/security/jwt_validator.py\n+++ b/src/security/jwt_validator.py\n@@ -18,2 +18,3 @@\n-    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})\n+    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": True})` },
      { step: 5, time: '00:00:11', tag: 'SAFETY', tagClass: 'term-info', text: 'SAFETY_GUARD: Verified diff compliance with GitHub branch protection policies.' },
      { step: 6, time: '00:00:14', tag: 'VERIFY', tagClass: 'term-verify', text: 'ACTION: terminal.run("pytest tests/test_auth.py")' },
      { step: 6, time: '00:00:16', tag: 'PYTEST', tagClass: 'term-info', text: 'PASSED: 28/28 tests passed. Expired token rejection verified.' },
      { step: 7, time: '00:00:18', tag: 'SUCCESS', tagClass: 'term-success', text: 'PR CREATED: Opened Pull Request #120 "fix(security): enforce verify_exp in JWT decoding".' }
    ]
  },
  memory_leak: {
    title: 'Issue #133: Stream Unclosed Async Buffer',
    steps: [
      { step: 1, time: '00:00:01', tag: 'WEBHOOK', tagClass: 'term-webhook', text: 'Ingested webhook event: issue_comment "@agent fix" on OpenFlaw#133' },
      { step: 2, time: '00:00:02', tag: 'SANDBOX', tagClass: 'term-sandbox', text: 'Provisioned clean E2B microVM [id: vm-e90b21]' },
      { step: 3, time: '00:00:04', tag: 'AST_MAP', tagClass: 'term-ast', text: 'Indexed stream buffers in src/io/stream_handler.py' },
      { step: 4, time: '00:00:06', tag: 'REACT', tagClass: 'term-react', text: 'THOUGHT: Context manager missing around async stream buffer read loop.' },
      { step: 4, time: '00:00:08', tag: 'PATCH', tagClass: 'term-patch', text: 'ACTION: file_editor.replace_block(src/io/stream_handler.py)', diff: true, diffContent: `--- a/src/io/stream_handler.py\n+++ b/src/io/stream_handler.py\n@@ -15,4 +15,5 @@\n-    reader = await open_connection(host, port)\n-    data = await reader.read()\n+    async with open_connection(host, port) as reader:\n+        data = await reader.read()` },
      { step: 5, time: '00:00:10', tag: 'SAFETY', tagClass: 'term-info', text: 'SAFETY_GUARD: Diff verified. Safe syntax transform.' },
      { step: 6, time: '00:00:13', tag: 'VERIFY', tagClass: 'term-verify', text: 'ACTION: terminal.run("pytest tests/test_stream.py")' },
      { step: 6, time: '00:00:15', tag: 'PYTEST', tagClass: 'term-info', text: 'PASSED: 19/19 tests passed. No unclosed socket warnings.' },
      { step: 7, time: '00:00:17', tag: 'SUCCESS', tagClass: 'term-success', text: 'PR CREATED: Opened Pull Request #134 "fix(io): wrap stream reader in async context manager".' }
    ]
  }
};

/* =========================================================================
   SIMULATOR CONTROLLER
   ========================================================================= */
let isSimRunning = false;
let currentScenario = 'zero_division';
let simTimer = null;

function initSimulator() {
  const scenarioBtns = document.querySelectorAll('.scenario-btn');
  const runBtn = document.getElementById('runSimBtn');
  const resetBtn = document.getElementById('resetSimBtn');

  scenarioBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      if (isSimRunning) return;
      scenarioBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentScenario = btn.getAttribute('data-scenario');
      resetSimulator();
    });
  });

  runBtn.addEventListener('click', () => {
    if (isSimRunning) return;
    runSimulation();
  });

  resetBtn.addEventListener('click', () => {
    resetSimulator();
  });
}

function runSimulation() {
  isSimRunning = true;
  const runBtn = document.getElementById('runSimBtn');
  const runBtnIcon = document.getElementById('runBtnIcon');
  const runBtnText = document.getElementById('runBtnText');
  const simStatus = document.getElementById('simStatus');
  const terminal = document.getElementById('terminalOutput');
  const stepBadges = document.querySelectorAll('.step-badge');

  runBtn.disabled = true;
  runBtnIcon.textContent = '⏳';
  runBtnText.textContent = 'Agent Executing...';
  simStatus.textContent = 'RUNNING';
  simStatus.style.borderColor = '#ffffff';

  terminal.innerHTML = '';
  stepBadges.forEach(b => b.className = 'step-badge');

  const scenario = SIM_SCENARIOS[currentScenario];
  const steps = scenario.steps;
  let stepIndex = 0;

  function executeNextStep() {
    if (stepIndex >= steps.length) {
      isSimRunning = false;
      runBtn.disabled = false;
      runBtnIcon.textContent = '▶';
      runBtnText.textContent = 'Run Autonomous Agent';
      simStatus.textContent = 'COMPLETED';
      return;
    }

    const s = steps[stepIndex];

    // Update progress steps
    stepBadges.forEach(b => {
      const bStep = parseInt(b.getAttribute('data-step'));
      if (bStep < s.step) {
        b.className = 'step-badge completed';
      } else if (bStep === s.step) {
        b.className = 'step-badge active';
      } else {
        b.className = 'step-badge';
      }
    });

    // Append terminal line
    const lineEl = document.createElement('div');
    lineEl.className = 'term-line';
    
    let lineHTML = `
      <span class="term-time">[${s.time}]</span>
      <span class="term-tag ${s.tagClass}">[${s.tag}]</span>
      <span>${escapeHtml(s.text)}</span>
    `;

    if (s.diff && s.diffContent) {
      lineHTML += `<div class="term-diff">${formatDiff(s.diffContent)}</div>`;
    }

    lineEl.innerHTML = lineHTML;
    terminal.appendChild(lineEl);
    terminal.scrollTop = terminal.scrollHeight;

    stepIndex++;
    simTimer = setTimeout(executeNextStep, 950);
  }

  executeNextStep();
}

function resetSimulator() {
  if (simTimer) clearTimeout(simTimer);
  isSimRunning = false;

  const runBtn = document.getElementById('runSimBtn');
  const runBtnIcon = document.getElementById('runBtnIcon');
  const runBtnText = document.getElementById('runBtnText');
  const simStatus = document.getElementById('simStatus');
  const terminal = document.getElementById('terminalOutput');
  const stepBadges = document.querySelectorAll('.step-badge');

  runBtn.disabled = false;
  runBtnIcon.textContent = '▶';
  runBtnText.textContent = 'Run Autonomous Agent';
  simStatus.textContent = 'IDLE';

  stepBadges.forEach(b => b.className = 'step-badge');

  terminal.innerHTML = `
    <div class="term-line sys-line">
      <span class="term-time">[00:00:00]</span>
      <span class="term-tag term-info">[SYSTEM]</span>
      <span>OpenFlaw Worker daemon v1.0.0 listening for GitHub Webhook events.</span>
    </div>
    <div class="term-line sys-line">
      <span class="term-time">[00:00:00]</span>
      <span class="term-tag term-info">[READY]</span>
      <span>Selected scenario: ${SIM_SCENARIOS[currentScenario].title}. Click "Run Autonomous Agent" to begin.</span>
    </div>
  `;
}

function formatDiff(diffText) {
  const lines = diffText.split('\n');
  return lines.map(line => {
    if (line.startsWith('+') && !line.startsWith('+++')) {
      return `<div class="add">${escapeHtml(line)}</div>`;
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      return `<div class="del">${escapeHtml(line)}</div>`;
    }
    return `<div>${escapeHtml(line)}</div>`;
  }).join('');
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
}

/* =========================================================================
   TOOL TABS CONTROLLER
   ========================================================================= */
function initToolTabs() {
  const tabBtns = document.querySelectorAll('.tool-tab-btn');
  const display = document.getElementById('toolDetail');

  function renderTool(toolKey) {
    const data = TOOLS_DATA[toolKey];
    if (!data) return;

    display.innerHTML = `
      <div class="tool-header-group">
        <div>
          <h3 class="tool-main-title">${data.title}</h3>
          <div class="tool-file-path">${data.file}</div>
        </div>
        <span class="tool-badge">${data.type}</span>
      </div>
      <p class="tool-explanation">${data.description}</p>
      <pre class="tool-code-preview"><code>${escapeHtml(data.code)}</code></pre>
    `;
  }

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderTool(btn.getAttribute('data-tool'));
    });
  });

  // Initial render
  renderTool('repomap');
}

/* =========================================================================
   QUICKSTART TABS CONTROLLER
   ========================================================================= */
function initQuickstartTabs() {
  const tabs = document.querySelectorAll('.qs-tab');
  const panes = document.querySelectorAll('.qs-pane');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      panes.forEach(p => p.classList.remove('active'));

      tab.classList.add('active');
      const paneId = `pane-${tab.getAttribute('data-pane')}`;
      const targetPane = document.getElementById(paneId);
      if (targetPane) targetPane.classList.add('active');
    });
  });
}

/* =========================================================================
   COPY BUTTON CONTROLLER
   ========================================================================= */
function initCopyButtons() {
  const copyBtns = document.querySelectorAll('.copy-btn');

  copyBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-target');
      const targetEl = document.getElementById(targetId);
      if (!targetEl) return;

      const textToCopy = targetEl.innerText || targetEl.textContent;
      navigator.clipboard.writeText(textToCopy).then(() => {
        const originalText = btn.textContent;
        btn.textContent = 'COPIED!';
        btn.classList.add('copied');
        setTimeout(() => {
          btn.textContent = originalText;
          btn.classList.remove('copied');
        }, 2000);
      }).catch(() => {
        btn.textContent = 'FAILED';
      });
    });
  });
}
