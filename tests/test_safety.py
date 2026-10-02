"""Tests for the removal guards in diskwhy.safety."""

import os
import tempfile
import unittest

from diskwhy import safety


class IsActiveDbDirTest(unittest.TestCase):
    """Detection of data directories that a running server uses."""

    def test_matches_datadir_flag(self):
        cmds = [
            "/opt/homebrew/opt/mysql/bin/mysqld --datadir=/opt/homebrew/var/mysql --foo"
        ]
        self.assertTrue(safety.is_active_db_dir("/opt/homebrew/var/mysql", cmds))

    def test_matches_postgres_dash_D(self):
        cmds = [
            "/opt/homebrew/opt/postgresql@17/bin/postgres -D /opt/homebrew/var/postgresql@17"
        ]
        self.assertTrue(
            safety.is_active_db_dir("/opt/homebrew/var/postgresql@17", cmds)
        )

    def test_a_backup_sharing_a_prefix_is_not_active(self):
        cmds = ["/opt/homebrew/opt/mysql/bin/mysqld --datadir=/opt/homebrew/var/mysql"]
        self.assertFalse(
            safety.is_active_db_dir("/opt/homebrew/var/mysql.9.4-backup", cmds)
        )

    def test_no_processes_means_not_active(self):
        self.assertFalse(safety.is_active_db_dir("/opt/homebrew/var/postgresql@14", []))


class RemovalBlockerTest(unittest.TestCase):
    """The decision of whether a path may be removed."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=safety.HOME, prefix=".diskwhy-test-")
        self.addCleanup(lambda: os.system(f"rm -rf '{self.tmp}'"))

    def test_allows_an_ordinary_directory(self):
        d = os.path.join(self.tmp, "cache")
        os.mkdir(d)
        self.assertIsNone(safety.removal_blocker(d, []))

    def test_refuses_missing_path(self):
        self.assertEqual(
            safety.removal_blocker(os.path.join(self.tmp, "nope"), []),
            "path does not exist",
        )

    def test_refuses_relative_path(self):
        self.assertEqual(
            safety.removal_blocker("relative/path", []), "path must be absolute"
        )

    def test_refuses_outside_allowed_roots(self):
        self.assertIn("outside", safety.removal_blocker("/etc", []))
        self.assertIn("outside", safety.removal_blocker("/System", []))

    def test_refuses_protected_directories(self):
        for path in (safety.HOME, f"{safety.HOME}/Library", "/opt/homebrew/var"):
            if os.path.exists(path):
                self.assertIn("protected", safety.removal_blocker(path, []), path)

    def test_refuses_credentials_trees(self):
        ssh = f"{safety.HOME}/.ssh"
        if os.path.exists(ssh):
            self.assertIsNotNone(safety.removal_blocker(ssh, []))
            for entry in os.listdir(ssh)[:3]:
                self.assertIn(
                    "credentials", safety.removal_blocker(os.path.join(ssh, entry), [])
                )

    def test_refuses_dotdot_escape(self):
        sneaky = os.path.join(self.tmp, "..", "..", "etc")
        self.assertIsNotNone(safety.removal_blocker(sneaky, []))

    def test_symlink_is_judged_as_the_link_not_its_target(self):
        link = os.path.join(self.tmp, "link-to-etc")
        os.symlink("/etc", link)
        self.assertIsNone(safety.removal_blocker(link, []))

    def test_symlink_through_a_parent_into_a_protected_tree_is_refused(self):
        via = os.path.join(self.tmp, "via")
        os.symlink("/etc", via)
        self.assertIn("outside", safety.removal_blocker(os.path.join(via, "hosts"), []))

    def test_refuses_active_database_directory(self):
        data = os.path.join(self.tmp, "pgdata")
        os.mkdir(data)
        open(os.path.join(data, "PG_VERSION"), "w").close()
        running = [f"postgres -D {data}"]
        self.assertIn("running database", safety.removal_blocker(data, running))

    def test_refuses_a_parent_containing_an_active_database(self):
        parent = os.path.join(self.tmp, "var")
        data = os.path.join(parent, "mysql")
        os.makedirs(data)
        open(os.path.join(data, "mysql.ibd"), "w").close()
        self.assertIn(
            "running database",
            safety.removal_blocker(parent, [f"mysqld --datadir={data}"]),
        )

    def test_allows_an_inactive_database_directory(self):
        data = os.path.join(self.tmp, "pgdata-old")
        os.mkdir(data)
        open(os.path.join(data, "PG_VERSION"), "w").close()
        self.assertIsNone(safety.removal_blocker(data, ["postgres -D /somewhere/else"]))


if __name__ == "__main__":
    unittest.main()
