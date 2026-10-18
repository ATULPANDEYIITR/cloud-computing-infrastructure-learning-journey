# Block Storage: Volumes, Snapshots, IOPS, Throughput, and Disk Attachment

## Scope

This repository models block storage as an operational system rather than treating it as a single concept.

The four primary areas are related but have different responsibilities:

- **Volumes** represent persistent block devices with capacity, a storage class, performance configuration, encryption state, and a lifecycle state.
- **Snapshots** represent point-in-time recovery artifacts derived from volumes. Snapshot lineage is modeled separately from live volume attachment because a backup artifact does not become a mounted disk merely because it exists.
- **IOPS and throughput** represent different performance dimensions. IOPS measures the number of I/O operations that can be serviced per second, while throughput measures the amount of data transferred per second. Workload behavior determines which dimension becomes the bottleneck.
- **Disk attachment** connects a block volume to a compute instance through a device path. Attachment has its own lifecycle and must not be confused with volume creation or snapshot creation.

The implementations use a cloud-style block-storage model with `gp3` and `io2` volume classes. The performance limits used by the examples are deliberately encoded as validation rules so that the examples behave consistently. They should not be interpreted as current pricing or provider-wide service documentation.

## Operational relationship

A useful way to distinguish the concepts is:

```text
                    +------------------+
                    |      Volume      |
                    | capacity         |
                    | type             |
                    | IOPS             |
                    | throughput       |
                    | encryption       |
                    +--------+---------+
                             |
               +-------------+-------------+
               |                           |
               v                           v
       +---------------+           +---------------+
       | Disk          |           | Snapshot      |
       | Attachment    |           | point-in-time |
       | instance      |           | recovery      |
       | device path   |           | lineage       |
       +---------------+           +---------------+
               |
               v
       +---------------+
       | Workload      |
       | random I/O    |
       | sequential I/O|
       +---------------+
               |
               v
       IOPS or throughput
       becomes bottleneck
