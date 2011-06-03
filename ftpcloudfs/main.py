# -*- encoding: utf-8 -*-
__author__ = "Chmouel Boudjnah <chmouel@chmouel.com>"
import sys
import socket
import logging
from logging.handlers import SysLogHandler

from optparse import OptionParser
from pyftpdlib import ftpserver

from server import RackspaceCloudAuthorizer, RackspaceCloudFilesFS, \
    get_abstracted_fs
from constants import version, default_address, default_port
from monkeypatching import MyDTPHandler


class Main(object):
    """ FTPCloudFS: A FTP Proxy Interface to Rackspace Cloud Files or
    OpenStack swift."""

    def __init__(self):
        self.options = None

    def setup_log(self):
        ''' Setup Logging '''

        def log(log_type, msg):
            """
            Dummy function.
            """
            log_type(u"%s: %s" % (__package__, msg))
        ftpserver.log = lambda msg: log(logging.info, msg)
        ftpserver.logline = lambda msg: log(logging.debug, msg)
        ftpserver.logerror = lambda msg: log(logging.error, msg)

        if self.options.log_level is True:
            self.options.log_level = logging.DEBUG

        if self.options.syslog is True:
            logger = logging.getLogger()
            try:
                handler = SysLogHandler(address='/dev/log',
                                        facility=SysLogHandler.LOG_DAEMON)
            except IOError:
                # fall back to UDP
                handler = SysLogHandler(facility=SysLogHandler.LOG_DAEMON)
            finally:
                logger.addHandler(handler)
                logger.setLevel(self.options.log_level)
        else:
            log_format = '%(asctime)-15s - %(levelname)s - %(message)s'
            logging.basicConfig(filename=self.options.log_file,
                                format=log_format,
                                level=self.options.log_level)

    def parse_arguments(self):
        ''' Parse Command Line Options '''
        parser = OptionParser(usage="%s [OPTIONS]....." % __package__)
        parser.add_option('-p', '--port',
                          type="int",
                          dest="port",
                          default=default_port,
                          help="Port to bind the server default: %d." % \
                              (default_port))

        parser.add_option('-b', '--bind-address',
                          type="str",
                          dest="bind_address",
                          default=default_address,
                          help="Address to bind by default: %s." % \
                              (default_address))

        parser.add_option('-a', '--auth-url',
                          type="str",
                          dest="authurl",
                          default=None,
                          help="Auth URL for alternate providers" + \
                              "(eg OpenStack)")

        parser.add_option('-s', '--service-net',
                          action="store_true",
                          dest="servicenet",
                          default=False,
                          help="Connect via Rackspace ServiceNet network.")

        parser.add_option('-v', '--verbose',
                          action="store_true",
                          dest="log_level",
                          default=logging.INFO,
                          help="Be verbose on logging.")

        parser.add_option('-f', '--foreground',
                          action="store_true",
                          dest="foreground",
                          default=False,
                          help="Do not attempt to daemonize but" + \
                              "run in foreground.")

        parser.add_option('-l', '--log-file',
                          type="str",
                          dest="log_file",
                          default=None,
                          help="Log File: Default stdout when in foreground")

        parser.add_option('--syslog',
                          action="store_true",
                          dest="syslog",
                          default=None,
                          help="Enable logging to the system logger " + \
                              "(daemon facility).")

        parser.add_option('--pid-file',
                          type="str",
                          dest="pid_file",
                          default=None,
                          help="Pid file location when in daemon mode.")

        parser.add_option('--uid',
                          type="int",
                          dest="uid",
                          default=None,
                          help="UID to drop the privilige to " + \
                              "when in daemon mode")

        parser.add_option('--gid',
                          type="int",
                          dest="gid",
                          default=None,
                          help="GID to drop the privilige to " + \
                              "when in daemon mode")

        (options, _) = parser.parse_args()
        self.options = options

    def run_server(self):
        """Run the main ftp server loop"""
        ftp_handler = ftpserver.FTPHandler
        ftp_handler.dtp_handler = MyDTPHandler

        ftp_handler.banner = 'Rackspace Cloud Files %s using %s' % \
            (version, ftp_handler.banner)
        ftp_handler.authorizer = RackspaceCloudAuthorizer()
        RackspaceCloudFilesFS.servicenet = self.options.servicenet
        RackspaceCloudFilesFS.authurl = self.options.authurl

        ftp_handler.abstracted_fs = staticmethod(get_abstracted_fs)

        try:
            ftp_handler.masquerade_address = \
                socket.gethostbyname(self.options.bind_address)
        except socket.gaierror, (_, errmsg):
            sys.exit('Address error: %s' % errmsg)

        ftpd = ftpserver.FTPServer((self.options.bind_address,
                                    self.options.port),
                                   ftp_handler)

        ftpd.serve_forever()

    def setup_daemon(self):
        import daemon
        from utils import PidFile
        import tempfile

        daemonContext = daemon.DaemonContext()

        if not self.options.pid_file:
            self.options.pid_file = "%s/ftpcloudfs.pid" % \
                (tempfile.gettempdir())

        #daemonContext.pidfile = PidFile(self.options.pid_file)

        if self.options.uid:
            daemonContext.uid = self.options.uid

        if self.options.gid:
            daemonContext.gid = self.options.gid

        return daemonContext

    def main(self):
        """ Main entry point"""
        self.parse_arguments()

        if self.options.foreground:
            self.setup_log()
            self.run_server()
            return

        daemonContext = self.setup_daemon()
        with daemonContext:
            self.setup_log()
            self.run_server()
