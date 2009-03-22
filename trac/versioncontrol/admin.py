# -*- coding: utf-8 -*-
#
# Copyright (C) 2008 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import sys

from trac.admin import IAdminCommandProvider, get_dir_list
from trac.core import *
from trac.util.text import print_table, printerr, printout
from trac.util.translation import _, ngettext
from trac.versioncontrol import IRepositoryChangeListener, RepositoryManager


class VersionControlAdmin(Component):
    """Version control administration component."""

    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods
    
    def get_admin_commands(self):
        yield ('repository add', '<repos> <dir> [type]',
               'Add a source repository',
               self._complete_add, self._do_add)
        yield ('repository alias', '<repos> <alias>',
               'Create an alias for a repository',
               self._complete_repos, self._do_alias)
        yield ('repository list', '',
               'List source repositories',
               None, self._do_list)
        yield ('repository notify', '<event> <repos> <rev> [rev] [...]',
               """Notify trac about repository events
               
               The event "changeset_added" notifies that new changesets have
               been added to a repository.
               
               The event "changeset_modified" notifies that existing changesets
               have been modified in a repository.
               """,
               self._complete_notify, self._do_notify)
        yield ('repository remove', '<repos>',
               'Remove a source repository',
               self._complete_repos, self._do_remove)
        yield ('repository rename', '<repos> <newname>',
               'Rename a source repository',
               self._complete_repos, self._do_rename)
        yield ('repository resync', '<repos> [rev]',
               """Re-synchronize trac with repositories
               
               When [rev] is specified, only that revision is synchronized.
               Otherwise, the complete revision history is synchronized. Note
               that this operation can take a long time to complete.
               If synchronization gets interrupted, it can be resumed later
               using the `sync` command.
               
               To synchronize all repositories, specify "*" as the repository.
               """,
               self._complete_repos, self._do_resync)
        yield ('repository sync', '<repos> [rev]',
               """Resume synchronization of repositories
               
               Similar to `resync`, but doesn't clear the already synchronized
               changesets. Useful for resuming an interrupted `resync`.
               
               To synchronize all repositories, specify "*" as the repository.
               """,
               self._complete_repos, self._do_sync)
    
    _notify_events = [each for each in IRepositoryChangeListener.__dict__
                      if not each.startswith('_')]
    
    def get_supported_types(self):
        rm = RepositoryManager(self.env)
        return [type_ for connector in rm.connectors
                for (type_, prio) in connector.get_supported_types()
                if prio >= 0]
    
    def _complete_add(self, args):
        if len(args) == 2:
            return get_dir_list(args[-1], True)
        elif len(args) == 3:
            return self.get_supported_types()
    
    def _complete_notify(self, args):
        if len(args) == 1:
            return self._notify_events
        elif len(args) == 2:
            rm = RepositoryManager(self.env)
            return [reponame or '(default)' for reponame
                    in rm.get_all_repositories()]
    
    def _complete_repos(self, args):
        if len(args) == 1:
            rm = RepositoryManager(self.env)
            return [reponame or '(default)' for reponame
                    in rm.get_all_repositories()]
    
    def _do_add(self, reponame, dir, type_=None):
        if reponame == '(default)':
            reponame = ''
        if type_ is not None and type_ not in self.get_supported_types():
            raise TracError(_("The repository type '%(type)s' is not "
                              "supported", type=type_))
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.executemany("INSERT INTO repository (id, name, value) "
                           "VALUES (%s, %s, %s)",
                           [(reponame, 'dir', dir), (reponame, 'type', type_)])
        db.commit()
        RepositoryManager(self.env).reload_repositories()
    
    def _do_alias(self, reponame, alias):
        if reponame == '(default)':
            reponame = ''
        if alias in ('', '(default)'):
            raise TracError(_("Invalid alias name '%(alias)s'", alias=alias))
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.executemany("INSERT INTO repository (id, name, value) "
                           "VALUES (%s, %s, %s)",
                           [(alias, 'dir', None), (alias, 'alias', reponame)])
        db.commit()
        RepositoryManager(self.env).reload_repositories()
    
    def _do_list(self):
        rm = RepositoryManager(self.env)
        values = []
        for (reponame, info) in sorted(rm.get_all_repositories().iteritems()):
            alias = ''
            if 'alias' in info:
                alias = info['alias'] or '(default)'
            values.append((reponame or '(default)', info.get('type', ''),
                           alias, info.get('dir', '')))
        print_table(values, [_('Name'), _('Type'), _('Alias'), _('Directory')])
    
    def _do_notify(self, event, reponame, *revs):
        if event not in self._notify_events:
            raise TracError(_('Unknown notify event "%s"' % event))
        rm = RepositoryManager(self.env)
        rm.notify(event, reponame, revs, None)
    
    def _do_remove(self, reponame):
        if reponame == '(default)':
            reponame = ''
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("DELETE FROM repository "
                       "WHERE id=%s AND name IN ('dir', 'type', 'alias')",
                       (reponame,))
        cursor.execute("DELETE FROM revision WHERE repos=%s", (reponame,))
        cursor.execute("DELETE FROM node_change WHERE repos=%s", (reponame,))
        db.commit()
        RepositoryManager(self.env).reload_repositories()
    
    def _do_rename(self, reponame, newname):
        if reponame == '(default)':
            reponame = ''
        if newname == '(default)':
            newname = ''
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("UPDATE repository SET id=%s WHERE id=%s",
                       (newname, reponame))
        cursor.execute("UPDATE revision SET repos=%s WHERE repos=%s",
                       (newname, reponame))
        cursor.execute("UPDATE node_change SET repos=%s WHERE repos=%s",
                       (newname, reponame))
        db.commit()
        RepositoryManager(self.env).reload_repositories()
    
    def _do_resync(self, reponame, rev=None, clean=True):
        rm = RepositoryManager(self.env)
        if reponame == '*':
            if rev is not None:
                raise TracError(_('Cannot synchronize a single revision '
                                  'on multiple repositories'))
            repositories = rm.get_real_repositories(None)
        else:
            if reponame == '(default)':
                reponame = ''
            repos = rm.get_repository(reponame, None)
            if repos is None:
                raise TracError(_("Unknown repository '%(reponame)s'",
                                  reponame=reponame or '(default)'))
            if rev is not None:
                repos.sync_changeset(rev)
                printout(_('%(rev)s resynced on %(reponame)s.', rev=rev,
                           reponame=repos.reponame or '(default)'))
                return
            repositories = [repos]
        
        from trac.versioncontrol.cache import CACHE_METADATA_KEYS
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        inval = False
        for repos in sorted(repositories, key=lambda r: r.reponame):
            reponame = repos.reponame
            printout(_('Resyncing repository history for %(reponame)s... ',
                       reponame=reponame or '(default)'))
            if clean:
                cursor.execute("DELETE FROM revision WHERE repos=%s",
                               (reponame,))
                cursor.execute("DELETE FROM node_change "
                               "WHERE repos=%s", (reponame,))
                cursor.executemany("DELETE FROM repository "
                                   "WHERE id=%s AND name=%s",
                                   [(reponame, k) for k in CACHE_METADATA_KEYS])
                cursor.executemany("INSERT INTO repository (id, name, value) "
                                   "VALUES (%s, %s, %s)", 
                                   [(reponame, k, '') 
                                       for k in CACHE_METADATA_KEYS])
                db.commit()
            if repos.sync(self._resync_feedback):
                inval = True
            cursor.execute("SELECT count(rev) FROM revision WHERE repos=%s",
                           (reponame,))
            for cnt, in cursor:
                printout(ngettext('%(num)s revision cached.',
                                  '%(num)s revisions cached.', num=cnt))
        if inval:
            self.config.touch()     # FIXME: Brute force
        printout(_('Done.'))

    def _resync_feedback(self, rev):
        sys.stdout.write(' [%s]\r' % rev)
        sys.stdout.flush()

    def _do_sync(self, reponame, rev=None):
        self._do_resync(reponame, rev, clean=False)

