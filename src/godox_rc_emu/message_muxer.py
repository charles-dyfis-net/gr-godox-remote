import numpy as np
from gnuradio import gr
import pmt

import time

class message_muxer(gr.sync_block):
    def __init__(self, repeat_count=5, time_between_repeats=1e-5, active_gain=50, inactive_gain=0, cutoff_time=4.0):
        gr.sync_block.__init__(
            self,
            name='Godox Message Muxer',
            in_sig=None,
            out_sig=None,
        )
        self.inPortName = pmt.intern('in')
        self.triggerPortName = pmt.intern('trigger')
        self.outPortName = pmt.intern('out')
        self.debugPortName = pmt.intern('debug')
        self.gainPortName = pmt.intern('gain')
        self.message_port_register_in(self.inPortName)
        self.message_port_register_in(self.triggerPortName)
        self.message_port_register_out(self.outPortName)
        self.message_port_register_out(self.gainPortName)
        self.message_port_register_out(self.debugPortName)
        self.set_msg_handler(self.inPortName, self.handle_msg)
        self.set_msg_handler(self.triggerPortName, self.trigger_now)
        # map from (group, chan) to (last_transmit_time, num_repeats_left, message)
        self.messages = {}
        self.last_send_time = None
        self.repeat_count = repeat_count
        self.time_between_repeats_ns = int(time_between_repeats * 1e9)
        self.active_gain = active_gain
        self.inactive_gain = inactive_gain
        self.cutoff_time_ns = int(cutoff_time * 1e9)
        self.last_set_gain = None
    def handle_msg(self, msg_pmt):
        msg = pmt.to_python(msg_pmt)
        chan = msg.get('chan')
        group = msg.get('group')
        self.messages[(chan, group)] = (0, self.repeat_count, pmt.to_pmt(msg))
        self.trigger_now()
    def trigger_now(self, *_):
        # idle? turn off gain
        if not self.messages:
            if self.last_set_gain != self.inactive_gain:
                current_time = time.time_ns()
                if current_time > ((self.last_send_time or 0) + self.cutoff_time_ns):
                    self.message_port_pub(self.gainPortName, pmt.to_pmt({"gain": self.inactive_gain}))
                    self.last_set_gain = self.inactive_gain
            return
        # otherwise? enable gain
        current_time = time.time_ns()
        if self.last_set_gain != self.active_gain:
            if current_time > ((self.last_send_time or 0) + self.cutoff_time_ns):
                self.message_port_pub(self.gainPortName, pmt.to_pmt({"gain": self.active_gain}))
                self.last_set_gain = self.active_gain
        # which messages are old enough to resend?
        all_msgs = [i for i in self.messages.items() if i[1][0] <= (current_time - self.time_between_repeats_ns)]
        if not all_msgs:
            self.message_port_pub(self.debugPortName, pmt.to_pmt(f'No messages left after time filter (current_time={current_time!r}, time_between_repeats_ns={self.time_between_repeats_ns!r}, items={self.messages.items()!r})'))
            return
        # ...sort by age so we resend the oldest first...
        all_msgs.sort(key=lambda item: item[1][0])
        (msg_key, (_, repeat_count, msg_pmt)) = all_msgs.pop(0)
        if repeat_count > 1:
            self.messages[msg_key] = (current_time, repeat_count-1, msg_pmt)
        else:
            del self.messages[msg_key]
        self.message_port_pub(self.outPortName, msg_pmt)
