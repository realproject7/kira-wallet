"""Optional local tool discovery. No catalog, wallet, install or payment calls."""
import re
import shutil
import subprocess

H402_SKILL = 'https://github.com/Steemhunt/h402-cli/blob/main/SKILL.md'
H402_INSTALL = 'npm install -g @h402/cli'
H402_PROMPT = ('Install @h402/cli from npm, read the official h402 skill at '+H402_SKILL+
              ', then check h402 --version. Installation does not authorize payments.')


def h402_status(config):
    enabled = config.get('integrations', {}).get('h402', {}).get('enabled', False)
    executable = shutil.which('h402')
    result = {'enabled': enabled, 'installed': executable is not None, 'version': None,
              'status': 'disabled' if not enabled else 'not_installed',
              'skill_url': H402_SKILL, 'install_command': H402_INSTALL,
              'install_prompt': H402_PROMPT, 'enabling_authorizes_payments': False,
              'note': 'Use your agent to discover and call h402 capabilities. Enabling this integration does not authorize payments.'}
    if enabled and executable:
        result['status'] = 'unavailable'
        try:
            probe = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=2)
            # Do not expose arbitrary subprocess diagnostics or local paths.
            version = re.fullmatch(r'(?:h402\s+)?v?(\d+\.\d+\.\d+(?:-[\w.-]+)?(?:\+[\w.-]+)?)', probe.stdout.strip())
            if probe.returncode == 0 and version:
                result.update(status='available', version=version[1])
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            pass
    return result
