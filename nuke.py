# :coding: utf-8
# :copyright: Copyright (c) 2015 ftrack

import getpass
import sys
import pprint
import logging
import re
import os
import argparse
import traceback
import subprocess
import time
import threading


tools_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
ftrack_connect_path = os.path.join(tools_path, 'ftrack',
                                'ftrack-connect_package', 'windows', 'current')

if __name__ == '__main__':
    sys.path.append(os.path.join(tools_path, 'ftrack', 'ftrack-api'))
    sys.path.append(os.path.join(ftrack_connect_path, 'common.zip'))
    os.environ['PYTHONPATH'] = os.path.join(ftrack_connect_path, 'common.zip')

    os.environ['PYTHONPATH'] += os.pathsep + os.path.join(tools_path, 'pyblish', 'pyblish')
    os.environ['PYTHONPATH'] += os.pathsep + os.path.join(tools_path, 'pyblish', 'pyblish-hiero')
    os.environ['PYTHONPATH'] += os.pathsep + os.path.join(tools_path, 'pyblish', 'pyblish-integration')
    os.environ['PYTHONPATH'] += os.pathsep + os.path.join(tools_path, 'pyblish', 'pyblish-nuke')
    os.environ['PYTHONPATH'] += os.pathsep + os.path.join(tools_path, 'pyblish', 'pyblish-qml')
    os.environ['PYTHONPATH'] += os.pathsep + os.path.join(tools_path, 'pyblish', 'pyblish-rpc')
    os.environ['PYTHONPATH'] += os.pathsep + os.path.join(tools_path, 'pyblish', 'python-qt5')

    os.environ['NUKE_PATH'] = os.pathsep + os.path.join(tools_path, 'pyblish',
                                    'pyblish-nuke', 'pyblish_nuke', 'nuke_path')
    os.environ['NUKE_PATH'] += os.pathsep + os.path.join(tools_path, 'ftrack',
                                                    'ftrack-tools')

    os.environ['HIERO_PLUGIN_PATH'] = os.path.join(tools_path, 'pyblish',
                                                    'pyblish-hiero', 'pyblish_hiero', 'hiero_plugin_path')

    os.environ['PYBLISHPLUGINPATH'] = ''
    sys.path.append(r'C:\Users\toke.jepsen\Desktop\library')

import ftrack
import ftrack_connect.application

class ApplicationThread(threading.Thread):
    def __init__(self, launcher, applicationIdentifier, context, task):
        self.stdout = None
        self.stderr = None
        threading.Thread.__init__(self)
        self.launcher = launcher
        self.applicationIdentifier = applicationIdentifier
        self.context = context
        self.task = task

        self.logger = logging.getLogger()

    def run(self):

        self.logger.info('start time log')

        timelog = ftrack.createTimelog(1, contextId=self.task.getId())
        start_time = time.time()

        self.launcher.launch(self.applicationIdentifier, self.context)

        duration = time.time() - start_time
        timelog.set('duration', value=duration)

        self.logger.info('end time log')

class LaunchApplicationAction(object):
    '''Discover and launch nuke.'''

    identifier = 'ftrack-connect-launch-nuke'

    def __init__(self, application_store, launcher):
        '''Initialise action with *applicationStore* and *launcher*.

        *applicationStore* should be an instance of
        :class:`ftrack_connect.application.ApplicationStore`.

        *launcher* should be an instance of
        :class:`ftrack_connect.application.ApplicationLauncher`.

        '''
        super(LaunchApplicationAction, self).__init__()

        self.logger = logging.getLogger()

        self.application_store = application_store
        self.launcher = launcher

    # newer version pop-up
    def version_get(self, string, prefix, suffix = None):
        """Extract version information from filenames.  Code from Foundry's nukescripts.version_get()"""

        if string is None:
           raise ValueError, "Empty version string - no match"

        regex = "[/_.]"+prefix+"\d+"
        matches = re.findall(regex, string, re.IGNORECASE)
        if not len(matches):
            msg = "No \"_"+prefix+"#\" found in \""+string+"\""
            raise ValueError, msg
        return (matches[-1:][0][1], re.search("\d+", matches[-1:][0]).group())

    def is_valid_selection(self, selection):
        '''Return true if the selection is valid.'''
        if (
            len(selection) != 1 or
            selection[0]['entityType'] != 'task'
        ):
            return False

        entity = selection[0]
        task = ftrack.Task(entity['entityId'])

        if task.getObjectType() != 'Task':
            return False

        return True

    def register(self):
        '''Register discover actions on logged in user.'''
        ftrack.EVENT_HUB.subscribe(
            'topic=ftrack.action.discover and source.user.username={0}'.format(
                getpass.getuser()
            ),
            self.discover
        )

        ftrack.EVENT_HUB.subscribe(
            'topic=ftrack.action.launch and source.user.username={0} '
            'and data.actionIdentifier={1}'.format(
                getpass.getuser(), self.identifier
            ),
            self.launch
        )

    def discover(self, event):
        '''Return discovered applications.'''

        if not self.is_valid_selection(
            event['data'].get('selection', [])
        ):
            return

        items = []
        applications = self.application_store.applications
        applications = sorted(
            applications, key=lambda application: application['label']
        )

        for application in applications:
            application_identifier = application['identifier']
            label = application['label']
            items.append({
                'actionIdentifier': self.identifier,
                'label': label,
                'icon': application.get('icon', 'default'),
                'applicationIdentifier': application_identifier
            })

        return {
            'items': items
        }

    def launch(self, event):
        '''Handle *event*.

        event['data'] should contain:

            *applicationIdentifier* to identify which application to start.

        '''
        # Prevent further processing by other listeners.
        event.stop()

        if not self.is_valid_selection(
            event['data'].get('selection', [])
        ):
            return

        applicationIdentifier = event['data']['applicationIdentifier']
        context = event['data'].copy()
        context['source'] = event['source']

        task = ftrack.Task(event['data']['selection'][0]['entityId'])
        type_name = task.getType().getName()

        # getting path to file
        path = ''
        try:
            asset = None
            component = None

            # search for asset with same name as task
            for a in task.getAssets(assetTypes=['scene']):
                if a.getName().lower() == task.getName().lower():
                    asset = a

            component_name = 'nuke_work'
            if 'hiero' in applicationIdentifier:
                component_name = 'hiero_work'

            for v in reversed(asset.getVersions()):
                if not v.get('ispublished'):
                    v.publish()

                for c in v.getComponents():
                    if c.getName() == component_name:
                        component = c

                if component:
                    break

            current_path = component.getFilesystemPath()
            self.logger.info('Component path: %s' % current_path)

            # get current file data
            current_dir = os.path.dirname(current_path)
            prefix = os.path.basename(current_path).split('v')[0]
            extension = os.path.splitext(current_path)[1]
            max_version = int(self.version_get(current_path, 'v')[1])
            current_version = max_version

            # comparing against files in the same directory
            new_version = False
            new_basename = None
            for f in os.listdir(current_dir):
                basename = os.path.basename(f)
                f_prefix = os.path.basename(basename).split('v')[0]
                if f_prefix == prefix and basename.endswith(extension):
                    if int(self.version_get(f, 'v')[1]) > max_version:
                        new_version = True
                        max_version = int(self.version_get(f, 'v')[1])
                        new_basename = f

            if new_version:
                path = os.path.join(current_dir, new_basename)
            else:
                path = current_path
        except:
            msg = "Couldn't find any file to launch:"
            msg += " %s" % traceback.format_exc()
            self.logger.info(msg)

        if not path:
            try:
                parent = task.getParent()
                asset = parent.getAsset(parent.getName(), 'scene')
                version = asset.getVersions()[-1]
                path = version.getComponent(name='nuke').getFilesystemPath()
            except:
                self.logger.info(traceback.format_exc())

        self.logger.info('Found path: %s' % path)

        # adding application and task environment
        environment = {}

        tools_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        pyblish_path = os.path.join(tools_path, 'pyblish')

        data = os.environ['PYBLISHPLUGINPATH'].split(os.pathsep)

        app_path = os.path.join(pyblish_path, 'pyblish-bumpybox',
                                    'pyblish_bumpybox', 'plugins', 'nuke')
        if 'hiero' in applicationIdentifier:
            app_path = os.path.join(pyblish_path, 'pyblish-bumpybox',
                                    'pyblish_bumpybox', 'plugins', 'hiero')

        data.append(app_path)
        data.append(os.path.join(pyblish_path, 'pyblish-deadline',
                                 'pyblish_deadline', 'plugins'))
        data.append(os.path.join(app_path, task.getType().getName().lower()))

        environment['PYBLISHPLUGINPATH'] = data

        context['environment'] = environment

        # launching the app
        applicationStore = ApplicationStore()
        applicationStore._modifyApplications(path)

        path = os.path.join(ftrack_connect_path, 'resource',
                            'ftrack_connect_nuke')
        launcher = ApplicationLauncher(applicationStore,
                                    plugin_path=os.environ.get(
                                    'FTRACK_CONNECT_NUKE_PLUGINS_PATH', path))

        myclass = ApplicationThread(launcher, applicationIdentifier, context,
                                                                        task)
        myclass.start()

        ftrack.EVENT_HUB.publishReply(event,
            data={
                'success': True,
                'message': 'Launched %s!' % applicationIdentifier
            }
        )


class ApplicationStore(ftrack_connect.application.ApplicationStore):

    def _modifyApplications(self, path=''):
        self.applications = self._discoverApplications(path=path)

    def _discoverApplications(self, path=''):
        '''Return a list of applications that can be launched from this host.

        An application should be of the form:

            dict(
                'identifier': 'name_version',
                'label': 'Name version',
                'path': 'Absolute path to the file',
                'version': 'Version of the application',
                'icon': 'URL or name of predefined icon'
            )

        '''
        applications = []
        launchArguments = []
        nukexLaunchArguments = ['--nukex']
        hieroLaunchArguments = ['--hiero']
        if path:
            launchArguments = [path]
            nukexLaunchArguments.append(path)
            hieroLaunchArguments.append(path)

        if sys.platform == 'win32':
            prefix = ['C:\\', 'Program Files.*']

            # Specify custom expression for Nuke to ensure the complete version
            # number (e.g. 9.0v3) is picked up.
            nuke_version_expression = re.compile(
                r'(?P<version>[\d.]+[vabc]+[\dvabc.]*)'
            )

            applications.extend(self._searchFilesystem(
                expression=prefix + ['Nuke.*', 'Nuke\d.+.exe'],
                versionExpression=nuke_version_expression,
                label='Nuke {version}',
                applicationIdentifier='nuke_{version}',
                icon='nuke',
                launchArguments=launchArguments
            ))

            # Add NukeX as a separate application
            applications.extend(self._searchFilesystem(
                expression=prefix + ['Nuke.*', 'Nuke\d.+.exe'],
                versionExpression=nuke_version_expression,
                label='NukeX {version}',
                applicationIdentifier='nukex_{version}',
                icon='nukex',
                launchArguments=nukexLaunchArguments
            ))

            # Add Hiero as a separate application
            applications.extend(self._searchFilesystem(
                expression=prefix + ['Nuke.*', 'Nuke\d.+.exe'],
                versionExpression=nuke_version_expression,
                label='Hiero {version}',
                applicationIdentifier='hiero_{version}',
                icon='hiero',
                launchArguments=hieroLaunchArguments
            ))

        self.logger.debug(
            'Discovered applications:\n{0}'.format(
                pprint.pformat(applications)
            )
        )

        return applications


class ApplicationLauncher(ftrack_connect.application.ApplicationLauncher):
    '''Custom launcher to modify environment before launch.'''

    def __init__(self, application_store, plugin_path):
        '''.'''
        super(ApplicationLauncher, self).__init__(application_store)

        self.plugin_path = plugin_path

    def launch(self, applicationIdentifier, context=None):
        '''Launch application matching *applicationIdentifier*.

        *context* should provide information that can guide how to launch the
        application.

        Return a dictionary of information containing:

            success - A boolean value indicating whether application launched
                      successfully or not.
            message - Any additional information (such as a failure message).

        '''
        # Look up application.
        applicationIdentifierPattern = applicationIdentifier
        if applicationIdentifierPattern == 'hieroplayer':
            applicationIdentifierPattern += '*'

        application = self.applicationStore.getApplication(
            applicationIdentifierPattern
        )

        if application is None:
            return {
                'success': False,
                'message': (
                    '{0} application not found.'
                    .format(applicationIdentifier)
                )
            }

        # Construct command and environment.
        command = self._getApplicationLaunchCommand(application, context)
        environment = self._getApplicationEnvironment(application, context)

        # Environment must contain only strings.
        self._conformEnvironment(environment)

        success = True
        message = '{0} application started.'.format(application['label'])

        try:
            options = dict(
                env=environment,
                close_fds=True
            )

            # Ensure that current working directory is set to the root of the
            # application being launched to avoid issues with applications
            # locating shared libraries etc.
            applicationRootPath = os.path.dirname(application['path'])
            options['cwd'] = applicationRootPath

            # Ensure subprocess is detached so closing connect will not also
            # close launched applications.
            if sys.platform == 'win32':
                options['creationflags'] = subprocess.CREATE_NEW_CONSOLE
            else:
                options['preexec_fn'] = os.setsid

            self.logger.debug(
                'Launching {0} with options {1}'.format(command, options)
            )
            process = subprocess.Popen(command, **options)
            # waiting on the process to terminate to inform time tracking
            process.wait()

        except (OSError, TypeError):
            self.logger.exception(
                '{0} application could not be started with command "{1}".'
                .format(applicationIdentifier, command)
            )

            success = False
            message = '{0} application could not be started.'.format(
                application['label']
            )

        else:
            self.logger.debug(
                '{0} application started. (pid={1})'.format(
                    applicationIdentifier, process.pid
                )
            )

        return {
            'success': success,
            'message': message
        }

    def _getApplicationEnvironment(
        self, application, context=None
    ):
        '''Override to modify environment before launch.'''

        # Make sure to call super to retrieve original environment
        # which contains the selection and ftrack API.
        environment = super(
            ApplicationLauncher, self
        )._getApplicationEnvironment(application, context)

        applicationIdentifier = application['identifier']

        for k in context['environment']:
            path = ''
            for p in context['environment'][k]:
                path += os.pathsep + p

            environment[k] = path[1:]

        entity = context['selection'][0]
        task = ftrack.Task(entity['entityId'])
        taskParent = task.getParent()

        try:
            environment['FS'] = str(int(taskParent.getFrameStart()))
        except Exception:
            environment['FS'] = '1'

        try:
            environment['FE'] = str(int(taskParent.getFrameEnd()))
        except Exception:
            environment['FE'] = '1'

        environment['FTRACK_TASKID'] = task.getId()
        environment['FTRACK_SHOTID'] = task.get('parent_id')

        nuke_plugin_path = os.path.abspath(
            os.path.join(
                self.plugin_path, 'nuke_path'
            )
        )
        environment = ftrack_connect.application.appendPath(
            nuke_plugin_path, 'NUKE_PATH', environment
        )

        nuke_plugin_path = os.path.abspath(
            os.path.join(
                self.plugin_path, 'ftrack_connect_nuke'
            )
        )
        environment = ftrack_connect.application.appendPath(
            self.plugin_path, 'FOUNDRY_ASSET_PLUGIN_PATH', environment
        )

        # Set the FTRACK_EVENT_PLUGIN_PATH to include the notification callback
        # hooks.
        environment = ftrack_connect.application.appendPath(
            os.path.join(
                self.plugin_path, 'crew_hook'
            ), 'FTRACK_EVENT_PLUGIN_PATH', environment
        )

        environment = ftrack_connect.application.appendPath(
            os.path.join(
                self.plugin_path, '..', 'ftrack_python_api'
            ), 'FTRACK_PYTHON_API_PLUGIN_PATH', environment
        )

        environment['NUKE_USE_FNASSETAPI'] = '1'

        return environment


def register(registry, **kw):
    '''Register hooks.'''
    # Validate that registry is the correct ftrack.Registry. If not,
    # assume that register is being called with another purpose or from a
    # new or incompatible API and return without doing anything.
    if registry is not ftrack.EVENT_HANDLERS:
        # Exit to avoid registering this plugin again.
        return

    # Create store containing applications.
    application_store = ApplicationStore()

    path = os.path.join(ftrack_connect_path, 'resource',
                        'ftrack_connect_nuke')
    launcher = ApplicationLauncher(application_store,
                                plugin_path=os.environ.get(
                                'FTRACK_CONNECT_NUKE_PLUGINS_PATH', path))

    # Create action and register to respond to discover and launch actions.
    action = LaunchApplicationAction(application_store, launcher)
    action.register()


def main(arguments=None):
    '''Set up logging and register action.'''
    if arguments is None:
        arguments = []

    parser = argparse.ArgumentParser()
    # Allow setting of logging level from arguments.
    loggingLevels = {}
    for level in (
        logging.NOTSET, logging.DEBUG, logging.INFO, logging.WARNING,
        logging.ERROR, logging.CRITICAL
    ):
        loggingLevels[logging.getLevelName(level).lower()] = level

    parser.add_argument(
        '-v', '--verbosity',
        help='Set the logging output verbosity.',
        choices=loggingLevels.keys(),
        default='info'
    )
    namespace = parser.parse_args(arguments)

    '''Register action and listen for events.'''
    logging.basicConfig(level=loggingLevels[namespace.verbosity])
    log = logging.getLogger()

    ftrack.setup()

    # Create store containing applications.
    application_store = ApplicationStore()

    path = os.path.join(ftrack_connect_path, 'resource',
                        'ftrack_connect_nuke')
    launcher = ApplicationLauncher(application_store,
                                plugin_path=os.environ.get(
                                'FTRACK_CONNECT_NUKE_PLUGINS_PATH', path))

    # Create action and register to respond to discover and launch actions.
    action = LaunchApplicationAction(application_store, launcher)
    action.register()

    ftrack.EVENT_HUB.wait()


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
