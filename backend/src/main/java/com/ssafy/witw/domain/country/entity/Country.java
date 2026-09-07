package com.ssafy.witw.domain.country.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
@Entity
@Table(name = "country")
public class Country {
    @Id
    @Size(max = 2)
    @Column(name = "country_code", nullable = false, length = 2)
    private String countryCode;

    @Size(max = 50)
    @NotNull
    @Column(name = "name_ko", nullable = false, length = 50)
    private String nameKo;

    @Size(max = 50)
    @NotNull
    @Column(name = "name_en", nullable = false, length = 50)
    private String nameEn;

    @Column(name = "latitude", nullable = false)
    private double latitude;

    @Column(name = "longitude", nullable = false)
    private double longitude;
}