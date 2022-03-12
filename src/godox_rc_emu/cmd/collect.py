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
       substr(content, 9, 8) AS brightness_bits,
       substr(content, 17, 2) AS cmd_bits,
       substr(content, 19, 6) AS color_bits,
       substr(content, 25, 8) AS cksum_bits,
       substr(content, 1, 16) AS hashed_bits
FROM raw_messages
WHERE length(content) = 33 AND seen_count > 2;

CREATE VIEW _parsed_messages_step1 AS
SELECT
    content,
    hashed_bits,
    grp_bits,        grp_bin2int.intval        AS grp_int,
    chan_bits,       chan_bin2int.intval       AS chan_int,
    brightness_bits, brightness_bin2int.intval AS brightness_int,
    cmd_bits,        cmd_bin2int.intval        AS cmd_int,
    color_bits,      color_bin2int.intval      AS color_int,
    cksum_bits,      cksum_bin2int.intval      AS cksum_int
FROM _parsed_message_bits
LEFT OUTER JOIN bin2int AS grp_bin2int        ON grp_bits = grp_bin2int.binstr
LEFT OUTER JOIN bin2int AS chan_bin2int       ON chan_bits = chan_bin2int.binstr
LEFT OUTER JOIN bin2int AS brightness_bin2int ON brightness_bits = brightness_bin2int.binstr
LEFT OUTER JOIN bin2int AS cmd_bin2int        ON cmd_bits = cmd_bin2int.binstr
LEFT OUTER JOIN bin2int AS color_bin2int      ON color_bits = color_bin2int.binstr
LEFT OUTER JOIN bin2int AS cksum_bin2int      ON cksum_bits = cksum_bin2int.binstr;

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
    iif(0 != brightness_int & 1, 49, 0) AS xor_brightness1,
    iif(0 != brightness_int & 2, 98, 0) AS xor_brightness2,
    iif(0 != brightness_int & 4, 196, 0) AS xor_brightness4,
    iif(0 != brightness_int & 8, 185, 0) AS xor_brightness8,
    iif(0 != brightness_int & 16, 67, 0) AS xor_brightness16,
    iif(0 != brightness_int & 32, 134, 0) AS xor_brightness32,
    iif(0 != brightness_int & 64, 61, 0) AS xor_brightness64
FROM _parsed_messages_step1;

CREATE VIEW _parsed_messages_step3 AS SELECT *,
    (~(xor_grp1 & xor_grp2)) & (xor_grp1|xor_grp2) as xor_part1a,
    (~(xor_grp4 & xor_grp8)) & (xor_grp4|xor_grp8) as xor_part1b,
    (~(xor_chan1 & xor_chan2)) & (xor_chan1|xor_chan2) as xor_part1c,
    (~(xor_chan4 & xor_chan8)) & (xor_chan4|xor_chan8) as xor_part1d,
    (~(xor_brightness1 & xor_brightness2)) & (xor_brightness1|xor_brightness2) as xor_part1e,
    (~(xor_brightness4 & xor_brightness8)) & (xor_brightness4|xor_brightness8) as xor_part1f,
    (~(xor_brightness16 & xor_brightness32)) & (xor_brightness16|xor_brightness32) as xor_part1g,
    xor_brightness64 as xor_part1h
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
    brightness_bits, brightness_int,
    cmd_bits, cmd_int,
    color_bits, color_int,
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
