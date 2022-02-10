import numpy as np
from gnuradio import gr
import pmt

class message_to_bitfield(gr.sync_block):
    """Given a stream of dicts with group, chan, value, cmd and color keys, generate a stream of uint8 vecs, each with a 0 or 1, indicating a high or low bit.

    If the input contains a cksum field, discard any messages where we calculate a different checksum. If it does not, calculate and use our own checksum.
    """

    def __init__(self):
        gr.sync_block.__init__(
            self,
            name='Godox Message->Bitfield',
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

        self.group_field = pmt.intern('group')
        self.chan_field = pmt.intern('chan')
        self.value_field = pmt.intern('value')
        self.cmd_field = pmt.intern('cmd')
        self.color_field = pmt.intern('color')
        self.cksum_field = pmt.intern('cksum')

        self.fmt = [
            # name, bit count, default
            (pmt.intern('group'), 4, pmt.to_pmt(1)),
            (pmt.intern('chan'), 4, pmt.to_pmt(0)),
            (pmt.intern('value'), 8, pmt.to_pmt(25)),
            (pmt.intern('cmd'), 2, pmt.to_pmt(0)),
            (pmt.intern('color'), 6, pmt.to_pmt(1)),
            (pmt.intern('cksum'), 8, pmt.PMT_NIL),
        ]

    def handle_msg(self, msg_pmt):
        if not pmt.is_dict(msg_pmt):
            self.message_port_pub(self.debugPortName, pmt.to_pmt(f'Expected a dict, got: {msg_pmt!r}'))
            return
        out_str = ''
        for (field_name_pmt, field_size, field_default) in self.fmt:
            field_val = pmt.to_python(pmt.dict_ref(msg_pmt, field_name_pmt, field_default))
            out_str += bin(field_val).lstrip('0b').zfill(field_size)
        out_str += '0' # all messages end with a trailing 0 as the 33rd bit
        self.message_port_pub(self.outPortName, pmt.to_pmt([1 if c == '1' else 0 for c in out_str]))
