import unittest
from guiagent_touch.events import extract_virtual, count_gestures


class EventTests(unittest.TestCase):
    def test_typeb_complete_and_filter(self):
        log=(
            b'add device 1: /dev/input/event6\n'
            b'  name:     "Virtual Touch Screen"\n'
            b'add device 2: /dev/input/event1\n'
            b'  name:     "input_mt_wrapper"\n'
            b'[ 123.000001] /dev/input/event6: EV_ABS       ABS_MT_TRACKING_ID   00000001\n'
            b'[ 123.000002] /dev/input/event6: EV_ABS       ABS_MT_POSITION_X   0000021c\n'
            b'[ 123.000003] /dev/input/event6: EV_SYN       SYN_REPORT         00000000\n'
            b'[ 123.000004] /dev/input/event1: EV_KEY       BTN_TOUCH          00000001\n'
            b'[ 123.100000] /dev/input/event6: EV_ABS       ABS_MT_TRACKING_ID   ffffffff\n'
            b'[ 123.100001] /dev/input/event6: EV_SYN       SYN_REPORT         00000000\n'
        )
        virtual, nodes=extract_virtual(log)
        self.assertEqual(nodes,['/dev/input/event6'])
        self.assertNotIn(b'event1',virtual)
        self.assertEqual(count_gestures(virtual)['complete_gestures'],1)
        self.assertTrue(count_gestures(virtual)['alignment_pass'])

    def test_unclosed_contact(self):
        ev=b'[ 2.0] EV_ABS ABS_MT_TRACKING_ID 00000001\n[ 2.1] EV_SYN SYN_REPORT 00000000\n'
        self.assertFalse(count_gestures(ev)['alignment_pass'])


if __name__=='__main__':unittest.main()
