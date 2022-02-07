import numpy as np
import pmt
from gnuradio import gr

class timings_to_bin(gr.sync_block):
    """Given a sequence of messages containing locations of rising and falling edges within a packet, try to decode that packet.
    """

    def __init__(self,
            # if True, we emit a string composed of '0's and '1's
            # if False, we emit a vector of uint8s, each of which is a 0 or 1
            textual_output=False,
            # should we ignore or queue partial messages?
            forward_partial=False,
            # How long should we see a high signal to start a message? Typical value 11e5-4
            hello_min=10e-4,
            hello_max=12e-4,
            # How long of a low signal indicates a 0? Typical value 6e-4
            low_min=5e-4,
            low_max=7e-4,
            # How long of a low signal can indicate a 1? Typical value 13e-4
            high_max=14e-4,
            # How long of a high signal can separate bits within a message? Typical value 7e-4
            sep_min=6e-4,
            sep_max=8e-4):
        gr.sync_block.__init__(
            self,
            name='Godox Binary Decoder',   # will show up in GRC
            in_sig=None,
            out_sig=None
        )
        self.hello_min = hello_min
        self.hello_max = hello_max
        self.low_min = low_min
        self.low_max = low_max
        self.high_max = high_max
        self.sep_min = sep_min
        self.sep_max = sep_max
        self.textual_output = textual_output
        self.forward_partial = forward_partial

        self.inPortName = pmt.intern('in')
        self.msgPortName = pmt.intern('out')
        self.debugPortName = pmt.intern('debug')

        self.message_port_register_in(self.inPortName)
        self.message_port_register_out(self.msgPortName)
        self.message_port_register_out(self.debugPortName)

        self.set_msg_handler(self.inPortName, self.handle_msg)

    def send_now(self, content, partial=None, with_warning=None):
        if partial is None:
            partial = with_warning is not None
        if with_warning:
            self.message_port_pub(self.debugPortName, pmt.to_pmt(with_warning))
        if not content:
            return False, content
        if partial and not self.forward_partial:
            return False, []
        if self.textual_output:
            self.message_port_pub(self.msgPortName, pmt.to_pmt(''.join('1' if item else '0' for item in content)))
        else:
            self.message_port_pub(self.msgPortName, pmt.to_pmt(content))
        return False, []

    def handle_msg(self, msg_pmt):
        """
        A valid input may contain only a sequence of (value, time) elements.

        Ignore content up to the first value that is high between hello_min and hello_max time units.
        After that value is seen, start decoding:
        - A span that is low between low_min and low_max indicates a 0
        - A span that is low between low_max and high_max indicates a 1
        - A span that is high between sep_min and sep_max (after a hello) divides two bits
        - Any span outside the above terminates decoding
        """
        msg = pmt.to_python(msg_pmt)
        in_msg = False
        content = []
        for item in msg:
            (item_val, item_time) = item
            if in_msg is False:
                if not item_val:
                    # hellos must be high
                    continue
                if item_time < self.hello_min:
                    continue
                if item_time > self.hello_max:
                    continue
                in_msg = True
                continue
            # below here, in_msg is true
            if item_val:
                # either this is a separator or the message is invalid
                if item_time < self.sep_min:
                    in_msg, content = self.send_now(content, f"Separator seen with duration {item_time}, less than minimum {self.sep_min}")
                    continue
                if item_time > self.sep_max:
                    # Invalid message, so we're counting it ended
                    in_msg, content = self.send_now(content, partial=True)
                    # high too long to be a separator; if it's within the hello range, consider it start of a new message
                    if item_time > self.hello_min and item_time < self.hello_max:
                        self.message_port_pub(self.debugPortName, pmt.to_pmt("Hello seen while already in a prior message; truncating and starting new"))
                        in_msg = True
                    else:
                        self.message_port_pub(self.debugPortName, pmt.to_pmt("Invalid long-high seen; ending message"))
                    continue
                # If we reached here, this separator is valid; no action to take
                continue
            # High branch closed with continue; we're processing a low period
            if item_time < self.low_min:
                in_msg, content = self.send_now(content, "Short-low timing of {item_time} below minimum of {self.low_min}")
                continue
            if item_time < self.low_max:
                content.append(0)
                continue
            if item_time > self.high_max:
                # No need for a warning here: This is expected after a legitimate message
                in_msg, content = self.send_now(content)
                continue
            content.append(1)
        self.send_now(content)

