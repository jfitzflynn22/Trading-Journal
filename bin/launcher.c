/*
 * Main executable for Trading Journal.app.
 *
 * This exists as a compiled binary rather than a shell script for one reason:
 * TCC. When an app bundle's main executable is a script, macOS execs the
 * interpreter (/bin/bash) and can attribute the app's file access to that
 * interpreter instead of to the bundle -- so a Full Disk Access grant on the
 * app has no effect, and reads under ~/Documents keep failing exactly as if
 * nothing had been granted. A Mach-O main executable is what the grant
 * attaches to, and its children inherit that responsibility.
 *
 * All it does is locate the project relative to itself and hand over to
 * bin/journal-launch.sh, which is shared with start-journal.command.
 *
 * Build (see bin/build-launcher.sh):
 *     clang -O2 -o "Trading Journal.app/Contents/MacOS/TradingJournal" bin/launcher.c
 */

#include <mach-o/dyld.h>
#include <libgen.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char exe[4096];
    uint32_t size = sizeof(exe);
    if (_NSGetExecutablePath(exe, &size) != 0) {
        fprintf(stderr, "cannot resolve own path\n");
        return 1;
    }

    /* .../Trading Journal.app/Contents/MacOS/TradingJournal
     * -> up four to the directory holding the bundle, which is the project. */
    char resolved[4096];
    if (realpath(exe, resolved) == NULL) {
        fprintf(stderr, "cannot resolve real path\n");
        return 1;
    }
    char *root = resolved;
    for (int i = 0; i < 4; i++) {
        root = dirname(root);
    }

    char script[4200];
    snprintf(script, sizeof(script), "%s/bin/journal-launch.sh", root);

    /* If the folder is still unreachable, say so where it can be seen. The
     * script cannot do this itself -- it is the thing that cannot be read --
     * and a bundle has no terminal to print to. */
    if (access(script, R_OK) != 0) {
        char log[4200];
        snprintf(log, sizeof(log),
                 "%s/Library/Application Support/TradingJournal/launcher.log",
                 getenv("HOME") ? getenv("HOME") : "/tmp");
        FILE *f = fopen(log, "a");
        if (f) {
            fprintf(f, "bundle blocked: cannot read %s\n", script);
            fclose(f);
        }
        execl("/usr/bin/osascript", "osascript", "-e",
              "display dialog \"Trading Journal still cannot read its own folder.\n\n"
              "If you have already granted Full Disk Access, remove the entry and add it "
              "again -- the app changed, and the old grant no longer matches it.\n\n"
              "Privacy & Security > Full Disk Access > select Trading Journal, press -, "
              "then + and re-add it from the trading-journal folder.\n\n"
              "start-journal.command always works without any permission.\" "
              "buttons {\"OK\"} default button 1 with title \"Trading Journal\" with icon caution",
              (char *)NULL);
        return 1;
    }

    /* Hand over wholesale: the shell script owns every other decision, so the
     * two entry points cannot drift apart. exec, not fork, so the app bundle's
     * process *is* the launcher -- that keeps the Dock tile and the TCC
     * identity attached to it for the life of the session.
     *
     * Arguments are passed through. That matters for --server-only, which the
     * LaunchAgent uses: launchd has no file access of its own under
     * ~/Documents, but this binary carries the app's signature and therefore
     * its Full Disk Access grant, so routing the service through here is what
     * lets the background server read the project at all. */
    if (argc > 1) {
        execl("/bin/bash", "bash", script, argv[1], (char *)NULL);
    }
    execl("/bin/bash", "bash", script, (char *)NULL);

    fprintf(stderr, "cannot exec %s\n", script);
    return 1;
}
