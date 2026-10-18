/*
 * Alternative Type-B single-contact executor for rootless Android ADB uinput.
 * Independent of original /data/local/tmp/uinput_tap_probe.
 * Compatible with existing EAD/AutoGLM wrapper CLI:
 *   tap x y dwell_ms [jitter_px]
 *   swipe x1 y1 x2 y2 dur_ms [curvature] [profile] [overshoot_px]
 * SINGLE CONTACT ONLY. Tested syntax locally; requires phone validation.
 * User-controlled phone + explicit consent; do not operate payments or irreversible UI.
 */
#define _DEFAULT_SOURCE
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <time.h>
#include <linux/uinput.h>
#include <errno.h>

void emit(int fd, int type, int code, int val) {
    struct input_event ie;
    memset(&ie, 0, sizeof(ie));
    ie.type = type;
    ie.code = code;
    ie.value = val;
    if (write(fd, &ie, sizeof(ie)) != (ssize_t)sizeof(ie)) { perror("write event"); exit(3); }
}

static void must_ioctl(int fd, unsigned long cmd, unsigned long arg, const char *desc) {
    if (ioctl(fd, cmd, arg) < 0) { perror(desc); exit(3); }
}
static void must_abs(int fd, struct uinput_abs_setup *arg, const char *desc) {
    if (ioctl(fd, UI_ABS_SETUP, arg) < 0) { perror(desc); exit(3); }
}
int setup_uinput(int x_max, int y_max) {
    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (fd < 0) { perror("open uinput"); return -1; }

    must_ioctl(fd, UI_SET_EVBIT, EV_ABS, "UI_SET_EVBIT EV_ABS");
    must_ioctl(fd, UI_SET_EVBIT, EV_KEY, "UI_SET_EVBIT EV_KEY");
    must_ioctl(fd, UI_SET_EVBIT, EV_SYN, "UI_SET_EVBIT EV_SYN");

    /* 让 Android 将设备识别为直接触摸屏，而不是触控板/指针设备 */
    must_ioctl(fd, UI_SET_PROPBIT, INPUT_PROP_DIRECT, "UI_SET_PROPBIT DIRECT");
    must_ioctl(fd, UI_SET_KEYBIT, BTN_TOUCH, "UI_SET_KEYBIT TOUCH");
    must_ioctl(fd, UI_SET_KEYBIT, BTN_TOOL_FINGER, "UI_SET_KEYBIT FINGER");
    must_ioctl(fd, UI_SET_ABSBIT, ABS_X, "UI_SET_ABSBIT X");
    must_ioctl(fd, UI_SET_ABSBIT, ABS_Y, "UI_SET_ABSBIT Y");
    must_ioctl(fd, UI_SET_ABSBIT, ABS_MT_SLOT, "UI_SET_ABSBIT MT_SLOT");
    must_ioctl(fd, UI_SET_ABSBIT, ABS_MT_TRACKING_ID, "UI_SET_ABSBIT TRACKING");
    must_ioctl(fd, UI_SET_ABSBIT, ABS_MT_POSITION_X, "UI_SET_ABSBIT MT_X");
    must_ioctl(fd, UI_SET_ABSBIT, ABS_MT_POSITION_Y, "UI_SET_ABSBIT MT_Y");

    struct uinput_abs_setup abs_x = {
        .code=ABS_MT_POSITION_X,
        .absinfo={.minimum=0, .maximum=x_max, .resolution=10}
    };
    struct uinput_abs_setup abs_y = {
        .code=ABS_MT_POSITION_Y,
        .absinfo={.minimum=0, .maximum=y_max, .resolution=10}
    };
    struct uinput_abs_setup abs_single_x = {
        .code=ABS_X,
        .absinfo={.minimum=0, .maximum=x_max, .resolution=10}
    };
    struct uinput_abs_setup abs_single_y = {
        .code=ABS_Y,
        .absinfo={.minimum=0, .maximum=y_max, .resolution=10}
    };

    struct uinput_abs_setup abs_slot = {
        .code=ABS_MT_SLOT, .absinfo={.minimum=0, .maximum=0}
    };
    struct uinput_abs_setup abs_id = {
        .code=ABS_MT_TRACKING_ID, .absinfo={.minimum=0, .maximum=65535}
    };
    must_abs(fd, &abs_slot, "UI_ABS_SETUP SLOT");
    must_abs(fd, &abs_id, "UI_ABS_SETUP TRACKING_ID");
    must_abs(fd, &abs_x, "UI_ABS_SETUP MT_X");
    must_abs(fd, &abs_y, "UI_ABS_SETUP MT_Y");
    must_abs(fd, &abs_single_x, "UI_ABS_SETUP X");
    must_abs(fd, &abs_single_y, "UI_ABS_SETUP Y");

    struct uinput_setup usetup;
    memset(&usetup, 0, sizeof(usetup));
    usetup.id.bustype = BUS_VIRTUAL;
    usetup.id.vendor = 0x1234;
    usetup.id.product = 0x5681;
    usetup.id.version = 3;
    strcpy(usetup.name, "Virtual Touch Screen");

    if (ioctl(fd, UI_DEV_SETUP, &usetup) < 0) { perror("UI_DEV_SETUP"); exit(3); }
    if (ioctl(fd, UI_DEV_CREATE) < 0) { perror("UI_DEV_CREATE"); exit(3); }

    /* 等待 Android InputReader 完成虚拟设备注册 */
    usleep(800000);
    return fd;
}

static double ease(double s, const char *profile) {
    if (strcmp(profile, "linear") == 0) return s;
    if (strcmp(profile, "ease_in") == 0) return s * s;
    if (strcmp(profile, "ease_out") == 0) return 1.0 - (1.0 - s) * (1.0 - s);
    return s < 0.5 ? 2 * s * s : 1.0 - pow(-2 * s + 2, 2) / 2.0;  /* ease_in_out */
}

static double gauss(double sd) {
    double u1 = (rand() + 1.0) / (RAND_MAX + 2.0);
    double u2 = (rand() + 1.0) / (RAND_MAX + 2.0);
    return sd * sqrt(-2.0 * log(u1)) * cos(2.0 * M_PI * u2);
}

void do_tap(int fd, int x, int y, int dwell_ms, int jitter_px) {
    if (jitter_px > 0) { x += (int)gauss(jitter_px / 2.0); y += (int)gauss(jitter_px / 2.0); }
    if (x < 0) x = 0;
    if (y < 0) y = 0;
    if (x > 1079) x = 1079;
    if (y > 2399) y = 2399;

    emit(fd, EV_ABS, ABS_MT_SLOT, 0);
    emit(fd, EV_ABS, ABS_MT_TRACKING_ID, 1);
    emit(fd, EV_ABS, ABS_MT_POSITION_X, x);
    emit(fd, EV_ABS, ABS_MT_POSITION_Y, y);
    emit(fd, EV_KEY, BTN_TOUCH, 1);
    emit(fd, EV_KEY, BTN_TOOL_FINGER, 1);
    emit(fd, EV_SYN, SYN_REPORT, 0);

    usleep(dwell_ms * 1000);

    emit(fd, EV_ABS, ABS_MT_TRACKING_ID, -1);
    emit(fd, EV_KEY, BTN_TOUCH, 0);
    emit(fd, EV_KEY, BTN_TOOL_FINGER, 0);
    emit(fd, EV_SYN, SYN_REPORT, 0);
}

void do_swipe(int fd, int x1, int y1, int x2, int y2,
              int dur_ms, double curvature, const char *profile, int overshoot_px) {
    int steps = dur_ms / 8;
    if (steps < 12) steps = 12;
    if (steps > 200) steps = 200;

    double dx = x2 - x1, dy = y2 - y1;
    double len = sqrt(dx * dx + dy * dy);
    double px = len > 0 ? -dy / len : 0.0;
    double py = len > 0 ?  dx / len : 0.0;
    double cx = (x1 + x2) / 2.0 + px * curvature * len;
    double cy = (y1 + y2) / 2.0 + py * curvature * len;

    double ox = x2, oy = y2;
    if (overshoot_px > 0 && len > 0) {
        ox = x2 + (dx / len) * overshoot_px;
        oy = y2 + (dy / len) * overshoot_px;
    }

    int last_x = x1, last_y = y1;   /* track final emitted coord for vanishing point */

    emit(fd, EV_ABS, ABS_MT_SLOT, 0);
    emit(fd, EV_ABS, ABS_MT_TRACKING_ID, 1);
    for (int i = 0; i <= steps; i++) {
        double s = (double)i / steps;
        double e = ease(s, profile);
        double mt = 1.0 - e;
        double bx = mt*mt*x1 + 2*mt*e*cx + e*e*ox;
        double by = mt*mt*y1 + 2*mt*e*cy + e*e*oy;
        bx += gauss(0.8);
        by += gauss(0.8);
        int xi = (int)(bx + 0.5), yi = (int)(by + 0.5);
        if (xi < 0) xi = 0;
        if (yi < 0) yi = 0;
        if (xi > 1079) xi = 1079;
        if (yi > 2399) yi = 2399;

        emit(fd, EV_ABS, ABS_MT_POSITION_X, xi);
        emit(fd, EV_ABS, ABS_MT_POSITION_Y, yi);
        if (i == 0) {
            emit(fd, EV_KEY, BTN_TOUCH, 1);
            emit(fd, EV_KEY, BTN_TOOL_FINGER, 1);
        }
        emit(fd, EV_SYN, SYN_REPORT, 0);
        last_x = xi; last_y = yi;

        double e_next = ease((double)(i + 1) / steps, profile);
        double frac = e_next - e; if (frac < 0) frac = 0;
        long dt_us = (long)(frac * dur_ms * 1000.0);
        if (dt_us < 1500) dt_us = 1500;
        usleep(dt_us);
    }

    /* settle-back from overshoot to true target */
    if (overshoot_px > 0) {
        int settle = 4;
        for (int j = 1; j <= settle; j++) {
            double s = (double)j / settle;
            int xi = (int)(ox + (x2 - ox) * s + gauss(0.6) + 0.5);
            int yi = (int)(oy + (y2 - oy) * s + gauss(0.6) + 0.5);
            if (xi < 0) xi = 0;
            if (xi > 1079) xi = 1079;
            if (yi < 0) yi = 0;
            if (yi > 2399) yi = 2399;
            emit(fd, EV_ABS, ABS_MT_POSITION_X, xi);
            emit(fd, EV_ABS, ABS_MT_POSITION_Y, yi);
            emit(fd, EV_SYN, SYN_REPORT, 0);
            last_x = xi; last_y = yi;
            usleep(12000);
        }
    }

    /* ---- VANISHING-POINT CONVENTION (required by paper's parser) ----
       The paper's data model expects the LAST sample to be a "finger-up"
       point whose x,y EQUAL the previous point (is_integral checks
       trace[-1]==trace[-2]; endX/endY use END_SAMPLE_XY_IDX=-2).
       So we emit one dwell point, then one identical point (NO jitter),
       then lift. These two must be byte-identical in x,y.            */
    emit(fd, EV_ABS, ABS_MT_POSITION_X, last_x);
    emit(fd, EV_ABS, ABS_MT_POSITION_Y, last_y);
    emit(fd, EV_SYN, SYN_REPORT, 0);          /* penultimate point (real end) */
    usleep(15000);
    emit(fd, EV_ABS, ABS_MT_POSITION_X, last_x);
    emit(fd, EV_ABS, ABS_MT_POSITION_Y, last_y);
    emit(fd, EV_SYN, SYN_REPORT, 0);          /* vanishing point, identical x,y */

    emit(fd, EV_ABS, ABS_MT_TRACKING_ID, -1);
    emit(fd, EV_KEY, BTN_TOUCH, 0);
    emit(fd, EV_KEY, BTN_TOOL_FINGER, 0);
    emit(fd, EV_SYN, SYN_REPORT, 0);
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        printf("Usage: uinput_typeb_agent tap x y dwell_ms [jitter_px]\n");
        printf("       uinput_typeb_agent swipe x1 y1 x2 y2 dur_ms [curvature] [velocity] [overshoot_px]\n");
        return 1;
    }

    /* Validate arguments BEFORE registering any Android input device. */
    if (strcmp(argv[1], "tap") == 0) {
        if (argc != 5 && argc != 6) { fprintf(stderr,"Bad tap args\n"); return 2; }
        if (atoi(argv[2])<0 || atoi(argv[2])>1079 || atoi(argv[3])<0 || atoi(argv[3])>2399 ||
            atoi(argv[4])<50 || atoi(argv[4])>500 || (argc==6 && (atoi(argv[5])<0 || atoi(argv[5])>25))) {
            fprintf(stderr,"Invalid tap pixel/dwell/jitter\n"); return 2;
        }
    } else if (strcmp(argv[1], "swipe") == 0) {
        if (argc<7 || argc>10 || atoi(argv[2])<0 || atoi(argv[2])>1079 ||
            atoi(argv[3])<0 || atoi(argv[3])>2399 || atoi(argv[4])<0 || atoi(argv[4])>1079 ||
            atoi(argv[5])<0 || atoi(argv[5])>2399 || atoi(argv[6])<150 || atoi(argv[6])>2000) {
            fprintf(stderr,"Invalid swipe args\n"); return 2;
        }
        if (argc>=9 && strcmp(argv[8],"linear") && strcmp(argv[8],"ease_in") &&
            strcmp(argv[8],"ease_out") && strcmp(argv[8],"ease_in_out")) {
            fprintf(stderr,"Unsupported swipe profile\n"); return 2;
        }
    } else { fprintf(stderr,"Unknown action\n"); return 2; }
    srand(time(NULL) ^ getpid());
    int fd = setup_uinput(1079, 2399);
    if (fd < 0) return 1;

    if (strcmp(argv[1], "tap") == 0 && argc >= 5) {
        int x = atoi(argv[2]), y = atoi(argv[3]), dur = atoi(argv[4]);
        int jit = (argc >= 6) ? atoi(argv[5]) : 0;
        printf("tap %d %d dwell=%dms jit=%d\n", x, y, dur, jit);
        do_tap(fd, x, y, dur, jit);

    } else if (strcmp(argv[1], "swipe") == 0 && argc >= 7) {
        int x1=atoi(argv[2]), y1=atoi(argv[3]);
        int x2=atoi(argv[4]), y2=atoi(argv[5]);
        int dur=atoi(argv[6]);
        double curv = 0.0;
        char profile[16] = "ease_in_out";
        int overshoot = 0;

        if (argc >= 8) {
            double a7 = atof(argv[7]);
            if (a7 <= 0.5 && a7 >= 0.0) curv = a7;
        }
        if (argc >= 9) { strncpy(profile, argv[8], sizeof(profile)-1); }
        if (argc >= 10) { overshoot = atoi(argv[9]); }

        printf("swipe (%d,%d)->(%d,%d) dur=%dms curv=%.3f vel=%s over=%d\n",
               x1,y1,x2,y2,dur,curv,profile,overshoot);
        do_swipe(fd, x1, y1, x2, y2, dur, curv, profile, overshoot);
    }

    /* 确保 Android 已经处理完最后一次 UP 事件 */
    usleep(300000);
    if (ioctl(fd, UI_DEV_DESTROY) < 0) { perror("UI_DEV_DESTROY"); return 3; }
    if (close(fd) < 0) { perror("close uinput"); return 3; }
    return 0;
}
