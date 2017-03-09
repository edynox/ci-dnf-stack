from __future__ import absolute_import
from __future__ import unicode_literals

from behave import register_type
from behave import then
from behave import when
import parse

import command_utils
import repo_utils
import table_utils

@parse.with_pattern(r"stdout|stderr")
def parse_stdout_stderr(text):
    return text

register_type(stdout_stderr=parse_stdout_stderr)

@when('I run "{command}"')
def step_i_run_command(ctx, command):
    """
    Run a ``{command}`` as subprocess, collect its output and returncode.
    """
    ctx.cmd_result = command_utils.run(ctx, command)

@when('I successfully run "{command}" in repository "{repository}"')
def step_i_successfully_run_command_in_repository(ctx, command, repository):
    repo = repo_utils.get_repo_dir(repository)
    ctx.assertion.assertIsNotNone(repo, "repository does not exist")
    ctx.cmd_result = command_utils.run(ctx, command, cwd=repo)
    ctx.assertion.assertEqual(ctx.cmd_result.returncode, 0)

@when('I successfully run "{command}"')
def step_i_successfully_run_command(ctx, command):
    step_i_run_command(ctx, command)
    step_the_command_should_pass(ctx)

@then("the command should pass")
def step_the_command_should_pass(ctx):
    ctx.assertion.assertEqual(ctx.cmd_result.returncode, 0)

@then("the command should fail")
def step_the_command_should_fail(ctx):
    ctx.assertion.assertNotEqual(ctx.cmd_result.returncode, 0)

@then("the command exit code is {values}")
def step_the_command_exit_code_is(ctx, values):
    """
    Compares the exit code of the previous command with a given value or comma separated list of values or ranges, e.g. '1,3,100-102'.
    """
    codes = []
    parts = values.split(',')
    for part in parts:
        if '-' in part:  # range a-b
            (lower, upper) = part.split('-', 1)
            lower = int(lower.strip())
            upper = int(upper.strip())
            codes.extend(range(lower, upper+1))
        else:
            codes.append(int(part.strip()))  # just plain number
    ctx.assertion.assertIn(ctx.cmd_result.returncode, codes)

@then("the command {stream:stdout_stderr} should match exactly")
def step_the_command_stream_should_match_exactly(ctx, stream):
    ctx.assertion.assertIsNotNone(ctx.text, "Multiline text is not provided")
    text = getattr(ctx.cmd_result, stream)
    ctx.assertion.assertMultiLineEqual(text, ctx.text)

@then("the command {stream:stdout_stderr} should be empty")
def step_the_command_stream_should_be_empty(ctx, stream):
    ctx.text = ""
    step_the_command_stream_should_match_exactly(ctx, stream)

@then('the command {stream:stdout_stderr} should match regexp "{regexp}"')
def step_the_command_stream_should_match_regexp(ctx, stream, regexp):
    text = getattr(ctx.cmd_result, stream)
    ctx.assertion.assertRegexpMatches(text, regexp)

@then('the command {stream:stdout_stderr} should not match regexp "{regexp}"')
def step_the_command_stream_should_not_match_regexp(ctx, stream, regexp):
    text = getattr(ctx.cmd_result, stream)
    ctx.assertion.assertNotRegexpMatches(text, regexp)

@then('history should match "{cmd}" with "{act}" and "{alt}" package')
@then('history should match "{cmd}" with "{act}" and "{alt}" packages')
@then('history "{range}" should match "{cmd}" with "{act}" and "{alt}" package')
@then('history "{range}" should match "{cmd}" with "{act}" and "{alt}" packages')
def step_history_contains(ctx, cmd, act, alt, range=""):
    step_i_run_command(ctx, 'dnf history ' + range)
    text = getattr(ctx.cmd_result, 'stdout')
    lines = text.split('\n')
    assert len(lines) > 3, 'No output'
    del lines[:3]
    match = False
    for line in lines:
        columns = line.split('|')
        words = [word.strip() for word in columns]
        # last member can be e.g. "1 >"
        words += words[-1].split()
        if set([cmd, act, alt]).issubset(set(words)):
            match = True
            break
    assert match, '"{}" with "{}" and "{}" packages not matched!'.format(cmd, act, alt)

@then('history userinstalled should')
def step_userinstalled_match(ctx):
    def pkgs_split(pkgs):
        for pkg in pkgs.split(","):
            yield pkg.strip()
    keys = ['Match', 'Not match']
    table = table_utils.parse_kv_table(ctx, ['Action', 'Packages'], keys)
    step_i_run_command(ctx, 'dnf history userinstalled')
    text = getattr(ctx.cmd_result, 'stdout')
    assert text, 'No output'
    for m in pkgs_split(table[keys[0]]):  # should be matched
        assert m in text, 'Package {} not matched as userinstalled'.format(m)
    for n in pkgs_split(table[keys[1]]):  # should not be matched
        assert n not in text,  'Package {} matched as userinstalled'.format(m)

@then('history info "{spec}" should match')
@then('history info should match')
def step_history_info(ctx, spec=""):
    def pkgs_split(pkgs):
        return pkgs.split(",")

    actions = ['Install', 'Erase', 'Upgrade', 'Upgraded', 'Reinstall', 'Downgrade']
    keys = ['Command Line', 'Return-Code'] + actions

    table = table_utils.parse_kv_table(ctx, ['Key', 'Value'], keys)
    step_i_run_command(ctx, 'dnf history info ' + spec)

    text = getattr(ctx.cmd_result, 'stdout')
    lines = text.split('\n')
    assert text and lines, 'No output'

    brpmdb = None
    erpmdb = None
    cmdline = None
    g_cmdline = table['Command Line'] if 'Command Line' in table else None
    retcode = None
    g_retcode = table['Return-Code'] if 'Return-Code' in table else None

    for line in lines:
        if 'Begin rpmdb' in line:
            brpmdb = line.split(':')

        if 'End rpmdb' in line:
            erpmdb = line.split(':')

        if brpmdb and erpmdb:
            assert len(brpmdb) == len(erpmdb) == 3, 'Unexpected rpmdb version format'
            assert brpmdb[2] != erpmdb[2], 'No change in rpmdb version'
            erpmdb = None

        if 'Return-Code' in line and g_retcode:
            retcode = line.split(':')
            assert len(retcode) == 2, 'Unexpected Return-Code format'
            rc = retcode[1].strip()
            assert rc == g_retcode, 'Return-Code "{}" not matched by "{}"'.format(rc, g_retcode)

        if 'Command Line' in line and g_cmdline:
            cmdline = line.split(':')
            assert len(cmdline) == 2, 'Unexpected Command Line format'
            cmd = cmdline[1].strip()
            assert cmd == g_cmdline, 'Command Line "{}" not matched by "{}"'.format(cmd, g_cmdline)

    assert brpmdb, 'Begin rpmdb version not found'

    if g_cmdline:
        assert cmdline, 'Command line not found'

    if g_retcode:
        assert retcode, 'Return-Code not found'

    for key in actions:
        if key in table:
            pkgs = pkgs_split(table[key])
            for line in lines:
                for pkg in pkgs:
                    if pkg in line and key in line:
                        pkgs.remove(pkg)
            assert not pkgs, '"{}" not matched as "{}"'.format(pkgs[0], key)
