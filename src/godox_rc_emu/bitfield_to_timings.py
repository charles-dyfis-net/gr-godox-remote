import numpy as np
from gnuradio import gr
import pmt

class bitfield_to_timings(gr.sync_block):
    def __init__(self, hello_time=13e-4, bit_low_time=6e-4, bit_high_time=13e-4, bit_sep_time=7e-4):
        gr.sync_block.__init__(
            self,
            name='Godox Bitfield -> Timings',   # will show up in GRC
            in_sig=None,
            out_sig=None,
        )

        self.inPortName = pmt.intern('in')
        self.outPortName = pmt.intern('out')
        self.debugPortName = pmt.intern('debug')
        self.message_port_register_in(self.inPortName)
        self.message_port_register_out(self.outPortName)
        self.message_port_register_out(self.debugPortName)
        self.set_msg_handler(self.inPortName, self.handle_msg)

        self.hello_time = hello_time
        self.bit_low_time = bit_low_time
        self.bit_high_time = bit_high_time
        self.bit_sep_time = bit_sep_time

    def handle_msg(self, msg_pmt):
        out = [(True, self.hello_time)]
        msg = pmt.to_python(msg_pmt)
        for bit in msg:
            if bit:
                out.append((False, self.bit_high_time))
            else:
                out.append((False, self.bit_low_time))
            out.append((True, self.bit_sep_time))
        self.message_port_pub(self.outPortName, pmt.to_pmt(out))
