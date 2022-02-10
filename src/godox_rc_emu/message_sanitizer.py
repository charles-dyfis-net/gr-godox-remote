import numpy as np
from gnuradio import gr
import pmt

def update_checksum(checksum, content, xor_values):
    current_bit = 1
    for xor_value in xor_values:
        if content & current_bit:
            checksum ^= xor_value
        current_bit <<= 1
    return checksum

class message_sanitizer(gr.sync_block):
    """
    Transform dictionary-style messages to ensure that values can be
    represented in binary form, and add a checksum.
    """
    def __init__(self, validate_incoming_checksum=True):
        gr.sync_block.__init__(
            self,
            name='Godox Message Sanitizer',
            in_sig=None,
            out_sig=None
        )
        self.inPortName = pmt.intern('in')
        self.outPortName = pmt.intern('out')
        self.debugPortName = pmt.intern('debug')
        self.message_port_register_in(self.inPortName)
        self.message_port_register_out(self.outPortName)
        self.message_port_register_out(self.debugPortName)
        self.set_msg_handler(self.inPortName, self.handle_msg)
        self.validate_incoming_checksum = validate_incoming_checksum

    def warn(self, s):
        self.message_port_pub(self.debugPortName, pmt.to_pmt(s))

    def handle_msg(self, msg_in_pmt):
        checksum = 0
        msg_in = pmt.to_python(msg_in_pmt)
        group = msg_in.pop('group', 1)
        if group < 0 or group > 15:
            self.warn(f'Invalid group {group!r}')
            group = 1
        checksum = update_checksum(checksum, group, [110, 220, 137, 35])
        chan = msg_in.pop('chan', 0)
        if chan < 0 or chan > 15:
            self.warn(f'Invalid channel {chan!r}')
            chan = 0
        checksum = update_checksum(checksum, chan, [244, 217, 131, 55])
        value = msg_in.pop('value', 25)
        if value < 0:
            self.warn(f'Coercing negative brightness {value!r} to 0')
            value = 0
        elif value > 127:
            value = 127 # we don't know how the 8th bit goes into the checksum
        checksum = update_checksum(checksum, value, [49, 98, 196, 185, 67, 134, 61])
        cmd = msg_in.pop('cmd', 0)
        if cmd < 0:
            self.warn(f'Coercing negative command {cmd!r} to 0')
            cmd = 0
        elif cmd > 3:
            self.warn(f'Coercing invalid command {cmd!r} to 0')
            cmd = 0
        # default is daylight temp; bicolor lights support largest brightness range here
        color = msg_in.pop('color', 24)
        if color < 0:
            self.warn(f'Coercing negative color {color!r} to 0')
            color = 0
        elif color > 63:
            self.warn(f'Coercing invalid color {color!r} to 24')
            color = 63
        orig_cksum = msg_in.pop('cksum', None)
        msg_out = {
            'group': group,
            'chan': chan,
            'value': value,
            'cksum': checksum,
            'cmd': cmd,
            'color': color,
        }
        if self.validate_incoming_checksum and orig_cksum is not None and orig_cksum != checksum:
            self.warn(f'Calculated checksum {checksum!r} for message {msg_out!r}, but originally had checksum {orig_cksum!r}')
        self.message_port_pub(self.outPortName, pmt.to_pmt(msg_out))
