from __future__ import print_function

import argparse
import os
import subprocess
import sys
import tempfile

import tools_version

PROG = 'mstprivhost'
TOOL_VERSION = "1.0.0"

CMD_HELP = """\
restrict:  Set host 1 (ARM) privileged, host 0 (x86_64) restricted.
privilege: Set host 1 (ARM) privileged, host 0 (x86_64) privileged
           (back to default).
"""

DESCRIPTION = """\
restrict or privilege host
Note: New configurations takes effect immediately.
Note: priviliged host - host has all supported privileges.
      restricted host - host is not allowed to modify global
      per port/parameters or access other hosts parametersis.

"""

DISABLE_RSHIM_HELP = """\
When TRUE, the host does not have an RSHIM function
to access the embedded CPU registers
mlxconfig_name: HOST_DISABLE_RSHIM
"""

DISABLE_TRACER_HELP = """\
When TRUE, the host will not be allowed to own the Tracer
mlxconfig_name: HOST_DISABLE_TRACER_OWNER
"""

DISABLE_COUNTER_RD_HELP = """\
When TRUE, the host will not be allowed to read Physical port counters
mlxconfig_name: HOST_DISABLE_PORT_COUNTER
"""

DISABLE_PORT_OWNER_HELP = """\
When TRUE, the host will not be allowed to be Port Owner
mlxconfig_name: HOST_DISABLE_PORT_OWNER
"""


def _log(level, msg, *args, **kw):
    if args:
        msg = msg % args
    print(level, msg, end=kw.get('end', '\n'))


def info(msg, *args, **kw):
    _log("-I-", msg, *args, **kw)


def error(msg, *args, **kw):
    _log("-E-", msg, *args, **kw)


class PrivilegeMgr(object):
    CMD_LINE = "mstconfig -d %s -f %s --yes set_raw"
    TITLE = "MLNX_RAW_TLV_FILE\n"
    RAW_BYTES = "0x03000204 0x07000083 0x00000000"

    LIMITED = 0x10000000
    DISABLE_PORT_OWNER = 0x01
    DISABLE_COUNTER_RD = 0x02
    DISABLE_TRACER = 0x04
    DISABLE_RSHIM = 0x08

    RESTRICT_BYTES = "0x03000204 0x07000083 0x00000000 0x1000000f"
    PRIVILEGE_BYTES = "0x03000204 0x07000083 0x00000000 0x00000000"

    def __init__(self, device, privilege, disable_rshim, disable_tracer,
                 disable_counter_rd, disable_port_owner):
        self._privilege = privilege
        self._device = device
        self._file_p = tempfile.NamedTemporaryFile(
            suffix='.raw', prefix="nvconfig_setting_")
        self._file_name = self._file_p.name
        self._nv_host_priv_conf = 0
        if not self._privilege:
            self._nv_host_priv_conf = self.LIMITED
            if disable_rshim:
                self._nv_host_priv_conf |= self.DISABLE_RSHIM
            if disable_tracer:
                self._nv_host_priv_conf |= self.DISABLE_TRACER
            if disable_counter_rd:
                self._nv_host_priv_conf |= self.DISABLE_COUNTER_RD
            if disable_port_owner:
                self._nv_host_priv_conf |= self.DISABLE_PORT_OWNER

    def prepare(self):
        info("preparing configuration file...", end='')
        self._file_p.write(self.TITLE)

        nv_host_priv_conf_str = '0x%08x' % self._nv_host_priv_conf
        conf_bytes = " ".join((self.RAW_BYTES, nv_host_priv_conf_str))
        self._file_p.write(conf_bytes)
        self._file_p.flush()
        print("Done!")

    @staticmethod
    def _exec_cmd(cmd):
        p = subprocess.Popen(cmd,
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             universal_newlines=True,
                             shell=True)
        stdout, stderr = p.communicate()
        exit_code = p.wait()

        return (exit_code, stdout, stderr)

    def configure(self):
        info("configuring device...", end='')
        cmd = self.CMD_LINE % (self._device, self._file_name)
        exit_code, stdout, stderr = self._exec_cmd(cmd)

        if exit_code != 0:
            print("Failed")
            print(stdout + stderr)
        else:
            print("Done!")
        return exit_code

    def cleanup(self):
        self._file_p.close()
        if os.path.isfile(self._file_name):
            os.remove(self._file_name)


def parse_args():
    parser = argparse.ArgumentParser(
        prog=PROG, description=DESCRIPTION,
        formatter_class=argparse.RawTextHelpFormatter,
        version=tools_version.GetVersionString(PROG, TOOL_VERSION))
    # options arguments
    options_group = parser.add_argument_group('Options')
    options_group.add_argument(
        '--device',
        '-d',
        required=True,
        help='Device to work with.')

    # command arguments
    command_group = parser.add_argument_group('Commands')
    command_group.add_argument(
        'command',
        nargs=1,
        choices=["r", "restrict", "p", "privilege"],
        help=CMD_HELP)
    options_group.add_argument('--disable_rshim', action="store_true",
                             help=DISABLE_RSHIM_HELP)
    options_group.add_argument('--disable_tracer', action="store_true",
                             help=DISABLE_TRACER_HELP)
    options_group.add_argument('--disable_counter_rd', action="store_true",
                             help=DISABLE_COUNTER_RD_HELP)
    options_group.add_argument('--disable_port_owner', action="store_true",
                             help=DISABLE_PORT_OWNER_HELP)
    args = parser.parse_args()
    if args.command[0] in ("p", "privilege"):
        if args.disable_rshim or args.disable_tracer or \
                args.disable_counter_rd or args.disable_port_owner:
            parser.error("disable flags are not allowed in privilege mode")
    return args


def main():
    args = parse_args()
    disable_rshim = args.disable_rshim
    disable_tracer = args.disable_tracer
    disable_counter_rd = args.disable_counter_rd
    disable_port_owner = args.disable_port_owner

    device = args.device

    command = args.command[0]
    if command in ("p", "privilege"):
        privilege = True
    elif command in ("r", "restrict"):
        privilege = False
    retcode = 0
    mgr = PrivilegeMgr(device, privilege, args.disable_rshim,
                       args.disable_tracer, args.disable_counter_rd,
                       args.disable_port_owner)
    try:
        mgr.prepare()
        retcode = mgr.configure()

    except Exception as exc:
        error("got an error: %s", str(exc))
        retcode = 1
    except(KeyboardInterrupt, SystemExit):
        print("\nInterrupted!\nExiting")
        retcode = 1
    finally:
        mgr.cleanup()
    return retcode


if __name__ == "__main__":
    sys.exit(main())
