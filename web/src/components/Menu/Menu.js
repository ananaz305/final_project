import React from 'react';
import Box from "@mui/material/Box";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import AccountBox from "@mui/icons-material/AccountBox";
import ListItemText from "@mui/material/ListItemText";
import Divider from "@mui/material/Divider";
import EditDocumentIcon from "@mui/icons-material/EditDocument";
import CalendarTodayIcon from "@mui/icons-material/CalendarToday";
import FolderSpecialIcon from "@mui/icons-material/FolderSpecial";
import NextLink from 'next/link';

export const Menu = ({ currentPage }) => {
    return (
        <>
            <Box sx={{ flexGrow: 0, height: '100%' }}>
                <List
                    sx={{ width: '100%', maxWidth: 360 }}
                    component="nav"
                >
                    <ListItemButton selected={currentPage === 'account'} href="/account" component={NextLink}>
                        <ListItemIcon>
                            <AccountBox/>
                        </ListItemIcon>
                        <ListItemText primary="My account"/>
                    </ListItemButton>
                    <Divider component="li"/>
                    <ListItemButton selected={currentPage === 'services'} href="/services" component={NextLink}>
                        <ListItemIcon>
                            <CalendarTodayIcon/>
                        </ListItemIcon>
                        <ListItemText primary="Services"/>
                    </ListItemButton>
                    <Divider component="li"/>
                    <ListItemButton selected={currentPage === 'departments'} href="/departments" component={NextLink}>
                        <ListItemIcon>
                            <FolderSpecialIcon/>
                        </ListItemIcon>
                        <ListItemText primary="Departments"/>
                    </ListItemButton>
                    <Divider component="li"/>
                    <ListItemButton selected={currentPage === 'documents'} href="/documents" component={NextLink}>
                        <ListItemIcon>
                            <EditDocumentIcon/>
                        </ListItemIcon>
                        <ListItemText primary="My documents"/>
                    </ListItemButton>
                </List>
            </Box>
            <Divider variant="fullWidth" orientation="vertical" flexItem/>
        </>
    )
}
