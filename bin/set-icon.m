/*
 * Set a file's or bundle's Finder icon.
 *
 *     set-icon <image.png> <target path>
 *
 * Used for the Safari web app: "Add to Dock" takes its icon from whatever
 * favicon Safari had at the time, which is not reliably ours, and the web app
 * bundle is signed by Safari so its Resources should not be edited. This uses
 * the same mechanism as Finder's Get Info > paste icon: the icon is attached
 * to the file, leaving the bundle's own contents and signature untouched.
 *
 * Build: clang -framework Cocoa -o bin/set-icon bin/set-icon.m
 */

#import <Cocoa/Cocoa.h>

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 3) {
            fprintf(stderr, "usage: %s <image.png> <target path>\n", argv[0]);
            return 2;
        }

        NSString *imagePath = [[NSString stringWithUTF8String:argv[1]]
                                  stringByExpandingTildeInPath];
        NSString *target = [[NSString stringWithUTF8String:argv[2]]
                               stringByExpandingTildeInPath];

        NSImage *image = [[NSImage alloc] initWithContentsOfFile:imagePath];
        if (image == nil) {
            fprintf(stderr, "cannot read image: %s\n", argv[1]);
            return 1;
        }
        if (![[NSFileManager defaultManager] fileExistsAtPath:target]) {
            fprintf(stderr, "no such target: %s\n", argv[2]);
            return 1;
        }

        BOOL ok = [[NSWorkspace sharedWorkspace] setIcon:image
                                                 forFile:target
                                                 options:0];
        if (!ok) {
            fprintf(stderr, "setIcon failed for %s\n", argv[2]);
            return 1;
        }
        printf("icon set on %s\n", argv[2]);
        return 0;
    }
}
