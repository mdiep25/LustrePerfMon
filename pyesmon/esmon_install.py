# pylint: disable=too-many-lines
"""

Install python RPMs for esmon_install to work properly first
"""
# Local libs
import logging
import re
from pyesmon import ssh_host
from pyesmon import esmon_install_common
from pyesmon import utils
from pyesmon import esmon_common


def iso_path_in_config(local_host):
    """
    Return the ISO path in the config file
    """
    local_host = ssh_host.SSHHost("localhost", local=True)
    command = (r"grep -v ^\# /etc/esmon_install.conf | "
               "grep ^iso_path: | awk '{print $2}'")

    retval = local_host.sh_run(command)
    if retval.cr_exit_status:
        logging.error("failed to run command [%s] on localhost, "
                      "ret = [%d], stdout = [%s], stderr = [%s]",
                      command,
                      retval.cr_exit_status,
                      retval.cr_stdout,
                      retval.cr_stderr)
        return None

    lines = retval.cr_stdout.splitlines()
    if len(lines) != 1:
        logging.error("unexpected iso path in config file: %s", lines)
        return None
    return lines[0]


class EsmonInstallServer(object):
    """
    ESMON server host has an object of this type
    """
    # pylint: disable=too-few-public-methods,too-many-instance-attributes
    def __init__(self, host, iso_dir):
        self.eis_host = host
        self.eis_iso_dir = iso_dir
        self.eis_rpm_dir = (iso_dir + "/" + "RPMS/" +
                            ssh_host.DISTRO_RHEL7)
        self.eis_rpm_dependent_dir = self.eis_rpm_dir + "/dependent"
        self.eis_rpm_dependent_fnames = None

    def eis_rpm_install(self, name):
        """
        Install a RPM in the ISO given the name of the RPM
        """
        if self.eis_rpm_dependent_fnames is None:
            command = "ls %s" % self.eis_rpm_dependent_dir
            retval = self.eis_host.sh_run(command)
            if retval.cr_exit_status:
                logging.error("failed to run command [%s] on host [%s], "
                              "ret = [%d], stdout = [%s], stderr = [%s]",
                              command,
                              self.eis_host.sh_hostname,
                              retval.cr_exit_status,
                              retval.cr_stdout,
                              retval.cr_stderr)
                return -1
            self.eis_rpm_dependent_fnames = retval.cr_stdout.split()

        rpm_dir = self.eis_rpm_dependent_dir
        rpm_pattern = (esmon_common.RPM_PATTERN_RHEL7 % name)
        rpm_regular = re.compile(rpm_pattern)
        matched_fname = None
        for filename in self.eis_rpm_dependent_fnames[:]:
            match = rpm_regular.match(filename)
            if match:
                matched_fname = filename
                logging.debug("matched pattern [%s] with fname [%s]",
                              rpm_pattern, filename)
                break
        if matched_fname is None:
            logging.error("failed to find RPM with pattern [%s] under "
                          "directory [%s] of host [%s]", rpm_pattern,
                          rpm_dir, self.eis_host.sh_hostname)
            return -1

        command = ("cd %s && rpm -ivh %s" %
                   (rpm_dir, matched_fname))
        retval = self.eis_host.sh_run(command)
        if retval.cr_exit_status:
            logging.error("failed to run command [%s] on host [%s], "
                          "ret = [%d], stdout = [%s], stderr = [%s]",
                          command,
                          self.eis_host.sh_hostname,
                          retval.cr_exit_status,
                          retval.cr_stdout,
                          retval.cr_stderr)
            return -1
        return 0


def dependency_do_install(local_host, mnt_path):
    """
    Install the pylibs
    """
    esmon_installer = EsmonInstallServer(local_host, mnt_path)
    for dependent_rpm in esmon_common.ESMON_INSTALL_DEPENDENT_RPMS:
        ret = local_host.sh_rpm_query(dependent_rpm)
        if ret == 0:
            continue
        ret = esmon_installer.eis_rpm_install(dependent_rpm)
        if ret:
            logging.error("failed to install rpm [%s] on host [%s]",
                          dependent_rpm, local_host .sh_hostname)
            return -1
    return 0


def dependency_install(local_host):
    """
    Install the missing pylib
    """
    iso_path = iso_path_in_config(local_host)
    if iso_path is None:
        iso_path = esmon_install_common.find_iso_path_in_cwd(local_host)
        if iso_path is None:
            logging.error("failed to find ESMON ISO %s under currect "
                          "directory")
            return -1
        logging.info("no [iso_path] is configured, use [%s] under current "
                     "directory", iso_path)

    mnt_path = "/mnt/" + utils.random_word(8)
    command = ("mkdir -p %s && mount -o loop %s %s" %
               (mnt_path, iso_path, mnt_path))
    retval = local_host.sh_run(command)
    if retval.cr_exit_status:
        logging.error("failed to run command [%s] on host [%s], "
                      "ret = [%d], stdout = [%s], stderr = [%s]",
                      command,
                      local_host.sh_hostname,
                      retval.cr_exit_status,
                      retval.cr_stdout,
                      retval.cr_stderr)
        return -1

    ret = dependency_do_install(local_host, mnt_path)
    if ret:
        logging.error("failed to install dependent libraries: %s")

    command = ("umount %s" % (mnt_path))
    retval = local_host.sh_run(command)
    if retval.cr_exit_status:
        logging.error("failed to run command [%s] on host [%s], "
                      "ret = [%d], stdout = [%s], stderr = [%s]",
                      command,
                      local_host.sh_hostname,
                      retval.cr_exit_status,
                      retval.cr_stdout,
                      retval.cr_stderr)
        ret = -1

    command = ("rmdir %s" % (mnt_path))
    retval = local_host.sh_run(command)
    if retval.cr_exit_status:
        logging.error("failed to run command [%s] on host [%s], "
                      "ret = [%d], stdout = [%s], stderr = [%s]",
                      command,
                      local_host.sh_hostname,
                      retval.cr_exit_status,
                      retval.cr_stdout,
                      retval.cr_stderr)
        ret = -1
    return ret


def main():
    """
    Install Exascaler monitoring
    """
    # pylint: disable=unused-variable
    missing_dependencies = []

    try:
        import yaml
    except ImportError:
        missing_dependencies.append("PyYAML")

    try:
        import requests
    except ImportError:
        missing_dependencies.append("python-requests")

    try:
        import filelock
    except ImportError:
        missing_dependencies.append("python2-filelock")

    try:
        import slugify
    except ImportError:
        missing_dependencies.append("python-slugify")

    try:
        import dateutil
    except ImportError:
        missing_dependencies.append("python-dateutil")

    local_host = ssh_host.SSHHost("localhost", local=True)
    for dependent_rpm in esmon_common.ESMON_INSTALL_DEPENDENT_RPMS:
        ret = local_host.sh_rpm_query(dependent_rpm)
        if ret == 0:
            missing_dependencies.append(dependent_rpm)

    if len(missing_dependencies):
        ret = dependency_install(local_host)
        if ret:
            logging.error("not able to install ESMON because some depdendency"
                          "RPMs are missing and not able to be installed: %s")
            return
    from pyesmon import esmon_install_nodeps
    esmon_install_nodeps.main()
