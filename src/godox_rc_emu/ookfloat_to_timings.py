import numpy as np
import pmt
from gnuradio import gr

class ookfloat_to_timings(gr.sync_block):
    """Given data with tags indicating regions of interest, and rising/falling edges within those regions, analyze for content

    sample_rate: Number of samples per second, used to transform offsets to times; if 1, time field will have offsets
    packet_tag: Tag that indicates start/end of a packet; collected data is sent when receiving packet_tag with value False (meaning a packet has ended)
    edge_tag: Tag that indicates rising/falling edges; only relevant within a packet

    Whenever a packet_tag of False is seen, dumps all the edge timings collected prior to that point, as a tuple of (bool, float) pairs
    """

    def __init__(self, sample_rate=1, packet_tag='packet', edge_tag='edge'):
        gr.sync_block.__init__(
            self,
            name='OOK Timing Detector',   # will show up in GRC
            in_sig=[np.float32],
            out_sig=None
        )
        self.outPortName = pmt.intern('out')
        self.debugPortName = pmt.intern('debug')
        self.message_port_register_out(self.outPortName)
        self.message_port_register_out(self.debugPortName)

        # Used to change offset to timestamp; setting to 1 keeps an offset
        self.sample_rate = sample_rate
        self.packet_tag = pmt.intern(packet_tag)
        self.edge_tag = pmt.intern(edge_tag)

        self.in_packet = False
        self.packet_content = None

        # Initial state; TODO: let the user override the default
        self.current_state = None
        # When non-None, this should be the offset of when the current_state was asserted
        self.state_start_time = None

    def work(self, input_items, output_items):
        in0 = input_items[0]
        tags = self.get_tags_in_window(0, 0, len(in0))
        for tag in tags:
            if not tag.key in (self.packet_tag, self.edge_tag):
                continue
            #print(f"IN: {(tag.offset, tag.key, tag.value)!r}")
            if tag.key is self.packet_tag:
                if tag.value is pmt.PMT_T:
                    # this is triggered by a rising edge; set the appropriate flags
                    self.in_packet = True
                    self.current_state = pmt.PMT_T
                    self.state_start_time = tag.offset
                    self.packet_content = []
                elif tag.value is pmt.PMT_F:
                    if self.packet_content is not None:
                        # Send our accumulated packet
                        self.message_port_pub(self.outPortName, pmt.to_pmt(self.packet_content))
                    # Reset state
                    self.state_start_time = self.current_state = self.packet_content = None
                    self.in_packet = False
                else:
                    self.message_port_pub(self.debugPortName, pmt.to_pmt("Unrecognized value seen in association with packet tag"))
            elif tag.key is self.edge_tag:
                if tag.value == self.current_state:
                    if tag.offset != self.state_start_time:
                        # if offset _is_ identical to start time, this packet is presumably also tagged as start-of-window
                        self.message_port_pub(self.debugPortName, pmt.to_pmt("Multiple edges seen for same state"))
                    continue
                if self.state_start_time is not None:
                    current_state_bool = pmt.to_python(self.current_state)
                    if self.sample_rate == 1:
                        time_in_state = tag.offset - self.state_start_time
                    else:
                        time_in_state = float(tag.offset - self.state_start_time) / self.sample_rate
                    self.packet_content.append((current_state_bool, time_in_state))
                else:
                    self.packet_content = [] # Yes, we can send an empty packet; I think this is okay.
                self.state_start_time = tag.offset
                self.current_state = tag.value
        self.consume(0, len(in0))
        return 0
