//go:build (amd64 || arm64) && !nosonic

// bytedance/sonic ships SIMD/asm-accelerated encode+decode for amd64 and arm64.
// On any other arch (or with -tags nosonic) nosonic.go stubs it out so the
// bench still builds and the sonic row is skipped rather than faked.
package record

import "github.com/bytedance/sonic"

var SonicAvailable = true

var CodecSonic = JSONCodec{
	Name:      "sonic",
	Marshal:   func(v any) ([]byte, error) { return sonic.Marshal(v) },
	Unmarshal: func(b []byte, v any) error { return sonic.Unmarshal(b, v) },
}
