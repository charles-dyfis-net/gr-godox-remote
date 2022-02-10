import numpy as np
import pmt
from gnuradio import gr

class timings_to_ookfloat(gr.sync_block):
    def __init__(self, sample_rate=1, true_value=1, false_value=0, idle_value=0, sep_time=1e-3, sep_value=0.0):
        gr.sync_block.__init__(
            self,
            name='Timings -> OOK',
            in_sig=None,
            out_sig=[np.float32],
        )
        self.inPortName = pmt.intern('in')
        self.debugPortName = pmt.intern('debug')
        self.message_port_register_in(self.inPortName)
        self.message_port_register_out(self.debugPortName)
        self.set_msg_handler(self.inPortName, self.handle_msg)

        self.sample_rate = float(sample_rate)
        self.true_value = float(true_value)
        self.false_value = float(false_value)
        self.idle_value = float(idle_value)
        self.sep_time = float(sep_time)
        self.sep_value = float(sep_value)

        self.queued_msgs = []

        self.current_msg = None
        self.current_bit_val = None
        self.current_bit_samples_remaining = 0

    def handle_msg(self, msg_pmt):
        # TODO: Discard messages when queue is too full? (If so, new messages, or old ones?)
        self.queued_msgs.append(pmt.to_python(msg_pmt) + [(self.sep_value, self.sep_time)])

    def work(self, input_items, output_items):
        out0 = output_items[0]

        buf_pos = 0
        output_space_remaining = len(out0)
        while output_space_remaining > 0:
            #print(f"Need to write {output_space_remaining} samples")
            # In the middle of a bit already; finish writing it
            if self.current_bit_samples_remaining:
                #print(f"  Writing {self.current_bit_samples_remaining} samples of value {self.current_bit_val}")
                samples_to_write = min(output_space_remaining, self.current_bit_samples_remaining)
                out0[buf_pos:buf_pos+samples_to_write] = self.current_bit_val
                buf_pos += samples_to_write
                output_space_remaining -= samples_to_write
                self.current_bit_samples_remaining -= samples_to_write
                continue
            # finished current message, but a new one is available
            if self.queued_msgs and not self.current_msg:
                self.current_msg = self.queued_msgs.pop(0)
                #print(f"  Message queue was empty; popped off message {self.current_msg}")
                continue
            # ready to start a new bit
            if self.current_msg:
                (new_bit, new_time) = self.current_msg.pop(0)
                if isinstance(new_bit, bool):
                    new_bit = self.true_value if new_bit else self.false_value
                self.current_bit_val = new_bit
                self.current_bit_samples_remaining = int(new_time * self.sample_rate)
                #print(f"  Pulling a new bit from the current message: {new_bit} for {new_time} == {self.current_bit_samples_remaining} samples")
                continue
            # if we reached here, no new bits remain; we're idle
            # FIXME: Maybe add some assertions to the effect of the above?
            #print(f"Nothing to do; writing idle_value from position {buf_pos} onward")
            out0[buf_pos:] = self.idle_value
            break
        #print(f"Finished writing {len(out0)} samples")
        return len(out0)
