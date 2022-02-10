import numpy as np
from gnuradio import gr
import pmt

class bitfield_to_message(gr.sync_block):
    """Take messages from Godox Binary Decoder; decode them into key/value pairs"""

    def __init__(self):  # only default arguments here
        gr.sync_block.__init__(
            self,
            name='Godox Bitfield->Message',
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


    def handle_msg(self, msg_pmt):
        """
        A valid input message shall consist of a stream of high and low bits.
        This may be represented either with a string containing 0s and 1s, or a
        vec of uint8s, each of which is either 1 or 0.

        Last bit is expected to be always low, so while we expect 33 bits of
        input, the meaningful subset can be encoded in 32.

        Output Fields:
        - data (precise fields teased out from the packet)
          * group (used to select which lights listen to this command)
          * chan (used to select which lights listen to this command)
          * value (integer with desired lighting level; integer percentage; RC-A5II only goes down to 25% with non-max colortemp, and 10% with max colortemp)
          * cmd (used to power lights on/off; not sure if other uses)
          * colortemp (integer from which desired color temperature is derived: 3200K + (colortemp*100K))
          * cksum (actual checksum present in the packet; only covers group/chan/value as inputs)
        """
        msg = pmt.to_python(msg_pmt)
        if len(msg) != 33:
            self.message_port_pub(self.debugPortName, pmt.to_pmt(f"Value of improper length seen; expected 33 bits, got {len(bits)}: {bits!r}"))
            return
        if isinstance(msg, (str, bytes)):
            msg_int = int(bits, 2)
        else:
            msg_int = 0
            for bit in msg:
                msg_int *= 2
                if bit:
                    msg_int += 1
        ## least significant bit should always be 0
        if msg_int % 2:
            self.message_port_pub(self.debugPortName, pmt.to_pmt(f"Unexpected message seen with last bit high: {msg!r}"))
            return
        msg_int >>= 1
        ## below here we're actually collecting data to use for output
        out = pmt.make_dict()
        ## next: checksum
        cksum = msg_int & 0xff
        out = pmt.dict_add(out, self.cksum_field, pmt.to_pmt(cksum))
        msg_int >>= 8
        ## next: color temperature
        color = msg_int & 0x3f
        out = pmt.dict_add(out, self.color_field, pmt.to_pmt(color))
        msg_int >>= 6
        ## next: cmd field
        cmd = msg_int & 0x03
        out = pmt.dict_add(out, self.cmd_field, pmt.to_pmt(cmd))
        msg_int >>= 2
        ## next: value field
        value = msg_int & 0xff
        out = pmt.dict_add(out, self.value_field, pmt.to_pmt(value))
        msg_int >>= 8
        ## next: chan field
        chan = msg_int & 0x0f
        out = pmt.dict_add(out, self.chan_field, pmt.to_pmt(chan))
        msg_int >>= 4
        ## last: group field
        grp = msg_int & 0x0f
        out = pmt.dict_add(out, self.group_field, pmt.to_pmt(grp))
        msg_int >>= 4
        if msg_int != 0:
            self.message_port_pub(self.debugPortName, pmt.to_pmt(f"High bits {msg_int!r} left after consuming expected content from message: {msg!r}"))
            return
        self.message_port_pub(self.outPortName, out)

