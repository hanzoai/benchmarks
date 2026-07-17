//go:build !((amd64 || arm64) && !nosonic)

// Fallback when sonic's asm backend is unavailable for this arch (or disabled
// via -tags nosonic): the sonic row is reported as unavailable, never faked.
package record

var SonicAvailable = false

var CodecSonic = JSONCodec{
	Name:      "sonic",
	Marshal:   func(v any) ([]byte, error) { return nil, errSonicUnavailable },
	Unmarshal: func(b []byte, v any) error { return errSonicUnavailable },
}

var errSonicUnavailable = errSonic{}

type errSonic struct{}

func (errSonic) Error() string { return "sonic unavailable on this arch/build" }
