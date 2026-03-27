"""
Global constants and nuclear data translation mappings for the andalus package.
"""

MT_TRANSLATION = {
    "total xs": (1),  # total cross section
    "mt 2 xs": (2),  # elastic scattering
    "mt 4 xs": (4),  # inelastic scattering
    "mt 16 xs": (16),  # (n,2n) reaction
    "mt 17 xs": (17),  # (n,3n) reaction
    "mt 18 xs": (18),  # fission reaction
    "mt 19 xs": (19),
    "mt 20 xs": (20),
    "mt 21 xs": (21),
    "mt 51 xs": (51),  # Production of neutron, with residual in nth excited state
    "mt 52 xs": (52),  # ...
    "mt 53 xs": (53),
    "mt 54 xs": (54),
    "mt 55 xs": (55),
    "mt 56 xs": (56),
    "mt 57 xs": (57),
    "mt 58 xs": (58),
    "mt 59 xs": (59),
    "mt 60 xs": (60),
    "mt 61 xs": (61),
    "mt 62 xs": (62),
    "mt 63 xs": (63),
    "mt 64 xs": (64),
    "mt 65 xs": (65),
    "mt 66 xs": (66),
    "mt 67 xs": (67),
    "mt 68 xs": (68),
    "mt 69 xs": (69),
    "mt 70 xs": (70),
    "mt 71 xs": (71),
    "mt 72 xs": (72),
    "mt 73 xs": (73),
    "mt 74 xs": (74),
    "mt 75 xs": (75),
    "mt 76 xs": (76),
    "mt 77 xs": (77),
    "mt 78 xs": (78),
    "mt 79 xs": (79),
    "mt 80 xs": (80),
    "mt 81 xs": (81),
    "mt 82 xs": (82),
    "mt 83 xs": (83),
    "mt 84 xs": (84),
    "mt 85 xs": (85),
    "mt 86 xs": (86),
    "mt 87 xs": (87),
    "mt 88 xs": (88),
    "mt 89 xs": (89),
    "mt 90 xs": (90),  # Production of neutron in 40th excited state
    "mt 91 xs": (91),
    "mt 102 xs": (102),  # (n,gamma) reaction
    "nubar total": (452),  # total neutron multiplicity
    "nubar delayed": (455),  # delayed neutron multiplicity
    "nubar prompt": (456),  # prompt neutron multiplicity
    "chi total": (35016),  # total fission neutron spectrum
    "chi delayed": (35017),  # delayed fission neutron spectrum
    "chi prompt": (35018),  # prompt fission neutron spectrum
    "ela leg mom 1": (3401),  # elastic scattering Legendre moment 1
    "ela leg mom 2": (3402),  # elastic scattering Legendre moment 2
    "ela leg mom 3": (3403),  # elastic scattering Legendre moment 3
    "ela leg mom 4": (3404),  # elastic scattering Legendre moment 4
}

PERT_LABELS = {
    1: "(n,tot.)",
    2: "(n,el.)",
    4: "(n,inl.)",
    16: "(n,2n)",
    18: "(n,fission)",
    19: "(n,f)",
    20: "(n,nf)",
    21: "(n,2nf)",
    22: "(n,nalpha)",
    102: "(n,gamma)",
    452: "nubar total",
    455: "nubar delayed",
    456: "nubar prompt",
    35018: "pfns",
}


def get_mt_number(label: str) -> int:
    """
    Safely convert a Serpent reaction string to an integer MT number.

    Parameters
    ----------
    label : str
        The reaction string from Serpent output.

    Returns
    -------
    int
        The corresponding MT number. Returns 999 if unknown to
        preserve integer type for HDF5 serialization.
    """
    return MT_TRANSLATION.get(label.lower(), 999)
