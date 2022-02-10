#!/usr/bin/env nix-shell
#!nix-shell -i python -p gnuradio.pythonEnv -p gnuradio.unwrapped.python.pkgs.pyzmq

import argparse
import sys

import pmt
import sqlite3
import zmq

ap = argparse.ArgumentParser()
ap.add_argument('--listen_socket', default='tcp://127.0.0.1:15263')
ap.add_argument('database', default='messages.sqlite')

ddl = '''
PRAGMA synchronous = OFF;
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS raw_messages(
    id INTEGER PRIMARY KEY,
    content BLOB UNIQUE,
    first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    seen_count INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bin2int(binstr BLOB NOT NULL PRIMARY KEY, intval INTEGER, fieldsize INTEGER);

DROP VIEW IF EXISTS parsed_messages;
DROP VIEW IF EXISTS _parsed_messages_step5;
DROP VIEW IF EXISTS _parsed_messages_step4;
DROP VIEW IF EXISTS _parsed_messages_step3;
DROP VIEW IF EXISTS _parsed_messages_step2;
DROP VIEW IF EXISTS _parsed_messages_step1;
DROP VIEW IF EXISTS _parsed_message_bits;

CREATE VIEW _parsed_message_bits AS
SELECT
       content,
       substr(content, 1, 4) AS grp_bits,
       substr(content, 5, 4) AS chan_bits,
       substr(content, 9, 8) AS value_bits,
       substr(content, 17, 2) AS cmd_bits,
       substr(content, 19, 6) AS temp_bits,
       substr(content, 25, 8) AS cksum_bits,
       substr(content, 1, 16) AS hashed_bits
FROM raw_messages
WHERE length(content) = 33 AND seen_count > 2;

CREATE VIEW _parsed_messages_step1 AS
SELECT
    content,
    hashed_bits,
    grp_bits,   grp_bin2int.intval   AS grp_int,
    chan_bits,  chan_bin2int.intval  AS chan_int,
    value_bits, value_bin2int.intval AS value_int,
    cmd_bits,   cmd_bin2int.intval   AS cmd_int,
    temp_bits,  temp_bin2int.intval  AS temp_int,
    cksum_bits, cksum_bin2int.intval AS cksum_int
FROM _parsed_message_bits
LEFT OUTER JOIN bin2int AS grp_bin2int   ON   grp_bits = grp_bin2int.binstr
LEFT OUTER JOIN bin2int AS chan_bin2int  ON  chan_bits = chan_bin2int.binstr
LEFT OUTER JOIN bin2int AS value_bin2int ON value_bits = value_bin2int.binstr
LEFT OUTER JOIN bin2int AS cmd_bin2int   ON   cmd_bits = cmd_bin2int.binstr
LEFT OUTER JOIN bin2int AS temp_bin2int  ON  temp_bits = temp_bin2int.binstr
LEFT OUTER JOIN bin2int AS cksum_bin2int ON cksum_bits = cksum_bin2int.binstr;

CREATE VIEW _parsed_messages_step2 AS
SELECT
    *,
    iif(0 != grp_int & 1, 110, 0) AS xor_grp1,
    iif(0 != grp_int & 2, 220, 0) AS xor_grp2,
    iif(0 != grp_int & 4, 137, 0) AS xor_grp4,
    iif(0 != grp_int & 8, 35, 0) AS xor_grp8,
    iif(0 != chan_int & 1, 244, 0) AS xor_chan1,
    iif(0 != chan_int & 2, 217, 0) AS xor_chan2,
    iif(0 != chan_int & 4, 131, 0) AS xor_chan4,
    iif(0 != chan_int & 8, 55, 0) AS xor_chan8,
    iif(0 != value_int & 1, 49, 0) AS xor_value1,
    iif(0 != value_int & 2, 98, 0) AS xor_value2,
    iif(0 != value_int & 4, 196, 0) AS xor_value4,
    iif(0 != value_int & 8, 185, 0) AS xor_value8,
    iif(0 != value_int & 16, 67, 0) AS xor_value16,
    iif(0 != value_int & 32, 134, 0) AS xor_value32,
    iif(0 != value_int & 64, 61, 0) AS xor_value64
FROM _parsed_messages_step1;

CREATE VIEW _parsed_messages_step3 AS SELECT *,
    (~(xor_grp1 & xor_grp2)) & (xor_grp1|xor_grp2) as xor_part1a,
    (~(xor_grp4 & xor_grp8)) & (xor_grp4|xor_grp8) as xor_part1b,
    (~(xor_chan1 & xor_chan2)) & (xor_chan1|xor_chan2) as xor_part1c,
    (~(xor_chan4 & xor_chan8)) & (xor_chan4|xor_chan8) as xor_part1d,
    (~(xor_value1 & xor_value2)) & (xor_value1|xor_value2) as xor_part1e,
    (~(xor_value4 & xor_value8)) & (xor_value4|xor_value8) as xor_part1f,
    (~(xor_value16 & xor_value32)) & (xor_value16|xor_value32) as xor_part1g,
    xor_value64 as xor_part1h
FROM _parsed_messages_step2;

CREATE VIEW _parsed_messages_step4 AS SELECT *,
    (~(xor_part1a & xor_part1b)) & (xor_part1a | xor_part1b) as xor_part2a,
    (~(xor_part1c & xor_part1d)) & (xor_part1c | xor_part1d) as xor_part2b,
    (~(xor_part1e & xor_part1f)) & (xor_part1e | xor_part1f) as xor_part2c,
    (~(xor_part1g & xor_part1h)) & (xor_part1g | xor_part1h) as xor_part2d
FROM _parsed_messages_step3;

CREATE VIEW _parsed_messages_step5 AS SELECT *,
    (~(xor_part2a & xor_part2b)) & (xor_part2a | xor_part2b) as xor_part3a,
    (~(xor_part2c & xor_part2d)) & (xor_part2c | xor_part2d) as xor_part3b
FROM _parsed_messages_step4;

CREATE VIEW parsed_messages AS SELECT
    content,
    hashed_bits,
    grp_bits, grp_int,
    chan_bits, chan_int,
    value_bits, value_int,
    cmd_bits, cmd_int,
    temp_bits, temp_int,
    cksum_bits, cksum_int,
    (~(xor_part3a & xor_part3b)) & (xor_part3a | xor_part3b) as cksum_int_calc
FROM _parsed_messages_step5;
'''

def populate_bin2int(conn):
    curs = conn.cursor()
    for fieldsize in (2, 4, 6, 8):
        for n in range((2**fieldsize)):
            curs.execute('INSERT OR IGNORE INTO bin2int(binstr, intval, fieldsize) VALUES(?, ?, ?)', (bin(n).lstrip('0b').zfill(fieldsize), n, fieldsize))
    conn.commit()


def main():
    args = ap.parse_args()
    print("Performing database setup...", file=sys.stderr)
    conn = sqlite3.connect(args.database)
    conn.executescript(ddl)
    populate_bin2int(conn)
    curs = conn.cursor()
    print("Performing message queue bind...", file=sys.stderr)
    context = zmq.Context()
    receiver = context.socket(zmq.PULL)
    with receiver.bind(args.listen_socket) as zmq_binding:
        print("Ready", file=sys.stderr)
        while True:
            content = pmt.to_python(pmt.deserialize_str(receiver.recv()))
            print(repr(content), file=sys.stderr)
            curs.execute('''INSERT INTO raw_messages(content) VALUES(?) ON CONFLICT(content) DO UPDATE SET seen_count = seen_count + 1, last_seen = CURRENT_TIMESTAMP''', (content,))
            conn.commit()

if __name__ == '__main__':
    main()
