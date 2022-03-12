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
    def __init__(self, validate_incoming_checksum=True, maintain_state=False, send_on_update=True,
            default_group=1, default_chan=0, default_brightness=25, default_color=24):
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
        self.maintain_state = maintain_state
        self.send_on_update = send_on_update
        # below will be updated iif maintain_state is True
        self.defaults = {
            'group': default_group,
            'chan': default_chan,
            'brightness': default_brightness,
            'color': default_color,
        }

    def set_chan(self, chan):
        self.defaults['chan'] = chan
    def set_group(self, group):
        self.defaults['group'] = group
    def set_color(self, color):
        self.defaults['color'] = color
        if self.send_on_update:
            self.handle_msg(None)
    def set_brightness(self, brightness):
        self.defaults['brightness'] = brightness
        if self.send_on_update:
            self.handle_msg(None)

    def warn(self, s):
        self.message_port_pub(self.debugPortName, pmt.to_pmt(s))

    def handle_msg(self, msg_in_pmt):
        checksum = 0
        if msg_in_pmt is None:
            msg_in = {}
        else:
            msg_in = pmt.to_python(msg_in_pmt)
        if not isinstance(msg_in, dict):
            if isinstance(msg_in, tuple):
                try:
                    msg_in = dict(msg_in)
                except ValueError as e:
                    self.warn(f'Received message in tuple form that could not be converted to a dict: {msg_in!r}: {e}')
                    return
            else:
                self.warn(f'Ignoring message which is not in either dict or tuple form')
                return
        group = msg_in.pop('group', self.defaults['group'])
        if group < 0 or group > 15:
            self.warn(f'Invalid group {group!r}')
            group = self.defaults['group']
        checksum = update_checksum(checksum, group, [110, 220, 137, 35])
        chan = msg_in.pop('chan', self.defaults['chan'])
        if chan < 0 or chan > 15:
            self.warn(f'Invalid channel {chan!r}')
            chan = self.defaults['chan']
        checksum = update_checksum(checksum, chan, [244, 217, 131, 55])
        brightness = msg_in.pop('brightness', self.defaults['brightness'])
        if brightness < 0:
            self.warn(f'Coercing negative brightness {brightness!r} to 0')
            brightness = 0
        elif brightness > 127:
            brightness = 127 # we don't know how the 8th bit goes into the checksum
        checksum = update_checksum(checksum, brightness, [49, 98, 196, 185, 67, 134, 61])
        cmd = msg_in.pop('cmd', 0)
        if cmd < 0:
            self.warn(f'Coercing negative command {cmd!r} to 0')
            cmd = 0
        elif cmd > 3:
            self.warn(f'Coercing invalid command {cmd!r} to 0')
            cmd = 0
        # default is daylight temp; bicolor lights support largest brightness range here
        color = msg_in.pop('color', self.defaults['color'])
        if color < 0:
            self.warn(f'Coercing negative color {color!r} to 0')
            color = 0
        elif color > 63:
            self.warn(f'Coercing invalid color {color!r} to 24')
            color = 63
        orig_cksum = msg_in.pop('cksum', None)
        msg_out = {
            'brightness': brightness,
            'chan': chan,
            'cksum': checksum,
            'cmd': cmd,
            'color': color,
            'group': group,
        }
        if self.maintain_state:
            self.defaults = msg_out
        if self.validate_incoming_checksum and orig_cksum is not None and orig_cksum != checksum:
            self.warn(f'Calculated checksum {checksum!r} for message {msg_out!r}, but originally had checksum {orig_cksum!r}')
        self.message_port_pub(self.outPortName, pmt.to_pmt(msg_out))
