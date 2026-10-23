# yyjson

Vendored unchanged from [ibireme/yyjson](https://github.com/ibireme/yyjson), tag
`0.13.0`, commit `6447536015f3d600f3d65323b10976103b337ca7`, on 2026-10-23.
MIT license retained in `LICENSE`. No network dependency during builds.

Used for strict JSON syntax and UTF-8 parsing. Numbers remain raw tokens so the
adapter can validate integers without floating-point rounding. Non-standard JSON
and unused writer/utility APIs are disabled in this build. This pins a host-side
parser dependency, not an ESP-IDF or board firmware version.

SHA-256 of upstream files:

```text
ef803cda5c06b8962face6dfa39c3284b3bcf3e73f4d7317664690cc779679ca  yyjson.h
d2d58ef0a3b2267862dc363832c4f3185fd375aea933d5d3419d1a940d6ece2e  yyjson.c
45e384d3d52c73cba3a64d6e6c25d47cd738cd8a55c30629e3201046eda62947  LICENSE
```
