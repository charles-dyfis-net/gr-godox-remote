Emulator for Godox RC-A5II Remote Control
=========================================

Have Godox lights using a 433mHz remote? (Tested with VL150 and VL300)

Own a HackRF, USRP, or other software-defined radio platform compatible with GNU radio?

Want to be able to control your lights programatically?


This project doesn't do that _yet_, but it already has collected data that should allow https://github.com/BrittonPlewes/GodoxRemote to be updated to calculate the checksum field internally.


Usage
=====

### Collecting wireless sequences

- Invoke `src/godox_rc_emu/cmd/collect.py` with the name of a SQLite database as an argument.
- Invoke the provided `send-to-zmq.grc` GNU Radio Companion flowgraph, with a suitable antenna attached.
- Operate your remote control.

After you have collected some data, open up the SQLite database created by the collect script; the most interesting tables are `raw_messages` and `parsed_messages`.

```none
sqlite> select * from parsed_messages where grp_int=1 and chan_int=0 and value_int=100;
┌───────────────────────────────────┬──────────────────┬──────────┬─────────┬───────────┬──────────┬────────────┬───────────┬──────────┬─────────┬───────────┬──────────┬────────────┬───────────┬────────────────┐
│              content              │   hashed_bits    │ grp_bits │ grp_int │ chan_bits │ chan_int │ value_bits │ value_int │ cmd_bits │ cmd_int │ temp_bits │ temp_int │ cksum_bits │ cksum_int │ cksum_int_calc │
├───────────────────────────────────┼──────────────────┼──────────┼─────────┼───────────┼──────────┼────────────┼───────────┼──────────┼─────────┼───────────┼──────────┼────────────┼───────────┼────────────────┤
│ 000100000110010000011000000100010 │ 0001000001100100 │ 0001     │ 1       │ 0000      │ 0        │ 01100100   │ 100       │ 00       │ 0       │ 011000    │ 24       │ 00010001   │ 17        │ 17             │
└───────────────────────────────────┴──────────────────┴──────────┴─────────┴───────────┴──────────┴────────────┴───────────┴──────────┴─────────┴───────────┴──────────┴────────────┴───────────┴────────────────┘
```


Notes
=====

The included `database.sqlite.sql` file is present as an example of what collected data looks like, to allow people without access to the relevant equipment to collect their own data (or without the time to spend flipping through groups and channels to build a test corpus) to get started quickly.

"Godox" is trademark of GODOX PHOTO EQUIPMENT CO, LTD. None of this software is written, endorsed, supported by, or otherwise associated with this company, and their name is used only to identify the equipment with which this project's software is intended to be compatible.
